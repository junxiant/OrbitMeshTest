import os
import sys
import uuid
from pathlib import Path
from typing import List, Optional

import json
import sqlite3
from contextlib import closing
import urllib.request
from fastapi import Depends, FastAPI, HTTPException, Response, Security, status
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

# Ensure project root is in Python sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.orchestrator import OrbitMeshOrchestrator
from src.core.config import ensure_dirs, DB_BACKEND, QDRANT_URL, QDRANT_PATH
from src.core.logging import logger
from src.state.session import SessionStateManager

ensure_dirs()

app = FastAPI(
    title="OrbitMesh Support API",
    description="FastAPI backend service for OrbitMesh diagnostic orchestrator",
    version="0.0.1",
)

# CORS configuration
default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://localhost:80",
    "http://127.0.0.1:80",
]
allowed_origins_raw = os.getenv("CORS_ORIGINS", "")
if allowed_origins_raw.strip():
    allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
else:
    allowed_origins = default_origins

is_wildcard = "*" in allowed_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=not is_wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_configured_api_key() -> str:
    key = os.getenv("API_KEY", os.getenv("ORBITMESH_API_KEY", "")).strip()
    if is_auth_required() and not key:
        logger.error("REQUIRE_API_KEY is enabled, but neither API_KEY nor ORBITMESH_API_KEY is set.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key authentication is misconfigured",
        )
    return key


def is_auth_required() -> bool:
    # Enabled by default if REQUIRE_API_KEY=true; otherwise optional for demo access
    val = os.getenv("REQUIRE_API_KEY", "false").lower().strip()
    return val in ("true", "1", "yes")


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    if not is_auth_required():
        # Authentication optional
        return api_key

    expected_key = get_configured_api_key()
    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key in X-API-Key header",
        )
    return api_key


orchestrator = OrbitMeshOrchestrator()


class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, description="Session ID for the conversation")
    message: str = Field(..., min_length=1, description="User input question or troubleshooting query")


class CitationResponse(BaseModel):
    source_id: str
    locator: str


class ChatResponse(BaseModel):
    session_id: str
    response: str
    citations: List[CitationResponse]
    action: str


def check_database_health() -> tuple[bool, dict]:
    """Verify database connection viability."""
    try:
        if SessionStateManager.is_postgres():
            with SessionStateManager._get_pg_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
            return True, {"backend": "postgres", "status": "connected"}
        else:
            db_path = SessionStateManager._db_path
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(str(db_path), timeout=5.0)) as conn:
                with conn:
                    conn.execute("SELECT 1;")
            return True, {"backend": "sqlite", "status": "connected"}
    except Exception as e:
        logger.warning(f"Database health check probe failed: {e}")
        return False, {"backend": DB_BACKEND, "status": "unhealthy", "error": str(e)}


def check_qdrant_health() -> tuple[bool, dict]:
    """Verify Qdrant vector database accessibility."""
    try:
        if QDRANT_URL:
            health_url = f"{QDRANT_URL.rstrip('/')}/healthz"
            req = urllib.request.Request(health_url, headers={"User-Agent": "OrbitMesh-HealthCheck"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return True, {"mode": "server", "url": QDRANT_URL, "status": "connected"}
                return False, {"mode": "server", "url": QDRANT_URL, "status": f"unexpected_status_{resp.status}"}
        else:
            if QDRANT_PATH.exists():
                return True, {"mode": "embedded", "path": str(QDRANT_PATH), "status": "ready"}
            return True, {"mode": "embedded", "path": str(QDRANT_PATH), "status": "uninitialized"}
    except Exception as e:
        logger.warning(f"Qdrant health check probe failed: {e}")
        return False, {"mode": "server" if QDRANT_URL else "embedded", "status": "unhealthy", "error": str(e)}


@app.get("/api/health")
def health_check():
    db_ok, db_info = check_database_health()
    qdrant_ok, qdrant_info = check_qdrant_health()
    overall = "ok" if (db_ok and qdrant_ok) else ("degraded" if db_ok else "unhealthy")
    return {
        "status": "ok",
        "health": overall,
        "service": "orbitmesh-backend",
        "version": "0.0.1",
        "dependencies": {
            "database": db_info,
            "vector_store": qdrant_info,
        },
    }


@app.get("/api/health/live")
def liveness_check():
    """Liveness probe: verifies the process is running."""
    return {"status": "alive"}


@app.get("/api/health/ready")
def readiness_check(response: Response):
    """Readiness probe: verifies critical dependencies before accepting traffic."""
    db_ok, db_info = check_database_health()
    qdrant_ok, qdrant_info = check_qdrant_health()

    if not db_ok or not qdrant_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "dependencies": {
                "database": db_info,
                "vector_store": qdrant_info,
            },
        }

    return {
        "status": "ready",
        "dependencies": {
            "database": db_info,
            "vector_store": qdrant_info,
        },
    }


@app.post("/api/chat", response_model=ChatResponse)
def process_chat(request: ChatRequest, _: Optional[str] = Depends(verify_api_key)):
    session_id = request.session_id.strip() if request.session_id else None
    if not session_id:
        session_id = f"web-{uuid.uuid4().hex[:8]}"

    try:
        envelope = orchestrator.process_turn(session_id, request.message)
    except Exception as e:
        logger.error(f"Orchestrator processing failed for session '{session_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestrator processing failed",
        )

    citations = [
        CitationResponse(source_id=c.source_id, locator=c.locator)
        for c in envelope.citations
    ]

    action_str = envelope.action.value if hasattr(envelope.action, "value") else str(envelope.action)

    return ChatResponse(
        session_id=session_id,
        response=envelope.response,
        citations=citations,
        action=action_str,
    )


@app.post("/api/chat/stream")
async def process_chat_stream(request: ChatRequest, _: Optional[str] = Depends(verify_api_key)):
    session_id = request.session_id.strip() if request.session_id else None
    if not session_id:
        session_id = f"web-{uuid.uuid4().hex[:8]}"

    async def event_generator():
        try:
            async for event_packet in orchestrator.process_turn_stream(session_id, request.message):
                event_name = event_packet.get("event", "message")
                data_payload = json.dumps(event_packet.get("data", {}))
                yield f"event: {event_name}\ndata: {data_payload}\n\n"
        except Exception as e:
            logger.error(f"Stream generation failed for session '{session_id}': {e}", exc_info=True)
            err_payload = json.dumps({"error": "Stream generation failed"})
            yield f"event: error\ndata: {err_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
