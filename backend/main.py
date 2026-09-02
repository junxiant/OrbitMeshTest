import os
import sys
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field

# Ensure project root is in Python sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.orchestrator import OrbitMeshOrchestrator
from src.core.config import ensure_dirs

ensure_dirs()

app = FastAPI(
    title="OrbitMesh Support API",
    description="FastAPI backend service for OrbitMesh diagnostic orchestrator",
    version="1.0.0",
)

# CORS configuration
allowed_origins_raw = os.getenv("CORS_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_configured_api_key() -> str:
    return os.getenv("API_KEY", os.getenv("ORBITMESH_API_KEY", "orbitmesh-secret-key"))


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


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "orbitmesh-backend",
        "version": "1.0.0",
    }


@app.post("/api/chat", response_model=ChatResponse)
def process_chat(request: ChatRequest, _: Optional[str] = Depends(verify_api_key)):
    session_id = request.session_id.strip() if request.session_id else None
    if not session_id:
        session_id = f"web-{uuid.uuid4().hex[:8]}"

    envelope = orchestrator.process_turn(session_id, request.message)

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


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)
