"""Comprehensive unit and integration test suite for the FastAPI backend.

Tests cover:
- Health check endpoints
- Chat turn processing and response envelope validation
- Request validation (empty strings, missing fields, type errors, whitespace IDs)
- Session ID generation, whitespace stripping, and preservation
- API Key authentication (both enforced and optional modes)
- CORS headers on preflight OPTIONS
- Multi-turn continuity across sequential requests
- Orchestrator exception containment returning structured 500
- Unicode, special characters, and large payload handling
- Action enum mapping (ask, instruct, escalate)
- OpenAPI schema and Swagger docs endpoints
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.main import app
from src.core.models import ResponseEnvelope, ActionEnum, Citation


@pytest.fixture
def client():
    """Fixture providing a FastAPI TestClient instance."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Health Check Endpoint Tests
# ---------------------------------------------------------------------------

def test_health_check_returns_ok(client):
    """Verify GET /api/health returns 200 OK and expected service metadata."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "orbitmesh-backend"
    assert "version" in data


# ---------------------------------------------------------------------------
# 2. Chat Endpoint Validation Tests
# ---------------------------------------------------------------------------

def test_chat_missing_message_fails_validation(client):
    """Verify sending a payload without 'message' returns 422 Unprocessable Entity."""
    response = client.post("/api/chat", json={})
    assert response.status_code == 422


def test_chat_empty_message_fails_validation(client):
    """Verify sending an empty message string returns 422 Unprocessable Entity."""
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_auto_generates_session_id(client):
    """Verify when session_id is omitted, the API generates a 'web-' prefixed ID."""
    response = client.post("/api/chat", json={"message": "My router has a red light"})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["session_id"].startswith("web-")
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 0
    assert "citations" in data
    assert "action" in data


def test_chat_preserves_provided_session_id(client):
    """Verify when session_id is supplied, it is preserved in the response."""
    custom_session = "custom-test-session-123"
    response = client.post(
        "/api/chat",
        json={"session_id": custom_session, "message": "My satellite node has an amber light"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == custom_session


def test_chat_whitespace_session_id_auto_generates_id(client):
    """Verify when session_id contains only whitespace, a new web- ID is generated."""
    response = client.post(
        "/api/chat",
        json={"session_id": "   ", "message": "My satellite node is flashing red"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"].startswith("web-")


def test_chat_non_string_types_fail_validation(client):
    """Verify non-string message or invalid types fail with 422."""
    response = client.post("/api/chat", json={"message": 12345})
    assert response.status_code == 422

    response_list = client.post("/api/chat", json={"message": ["invalid", "list"]})
    assert response_list.status_code == 422


def test_chat_malformed_json_body(client):
    """Verify invalid raw JSON body returns 422 or 400."""
    response = client.post(
        "/api/chat",
        content="{invalid-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code in (400, 422)


def test_chat_unicode_and_special_characters(client):
    """Verify messages with Unicode and special characters are handled cleanly."""
    unicode_query = "Comprobación del enrutador R1: ¿por qué parpadea en rojo? #@$!%*"
    response = client.post("/api/chat", json={"message": unicode_query})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 0


def test_chat_large_message_payload(client):
    """Verify messages with large payloads (>5000 characters) are processed without crashing."""
    large_query = "Detailed router log issue: " + ("solid amber light on node " * 250)
    response = client.post("/api/chat", json={"message": large_query})
    assert response.status_code == 200
    data = response.json()
    assert "response" in data


# ---------------------------------------------------------------------------
# 3. Response Envelope Structure Tests
# ---------------------------------------------------------------------------

def test_chat_response_structure_and_types(client):
    """Verify all fields in ChatResponse adhere to expected schema."""
    response = client.post(
        "/api/chat",
        json={"message": "How do I factory reset my router?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["response"], str)
    assert isinstance(data["action"], str)
    assert isinstance(data["citations"], list)
    for citation in data["citations"]:
        assert "source_id" in citation
        assert "locator" in citation


def test_chat_action_types_mapping(client):
    """Verify various ActionEnum values (ASK, ESCALATE) map correctly to string."""
    ask_envelope = ResponseEnvelope(
        response="Please confirm factory reset.",
        citations=[],
        action=ActionEnum.ASK,
    )
    with patch("backend.main.orchestrator.process_turn", return_value=ask_envelope):
        resp_ask = client.post("/api/chat", json={"message": "Reset device"})
        assert resp_ask.status_code == 200
        assert resp_ask.json()["action"] == "ask"

    escalate_envelope = ResponseEnvelope(
        response="Safety hazard detected. Disconnect immediately.",
        citations=[],
        action=ActionEnum.ESCALATE,
    )
    with patch("backend.main.orchestrator.process_turn", return_value=escalate_envelope):
        resp_esc = client.post("/api/chat", json={"message": "Device smoking"})
        assert resp_esc.status_code == 200
        assert resp_esc.json()["action"] == "escalate"


# ---------------------------------------------------------------------------
# 4. Authentication Tests
# ---------------------------------------------------------------------------

def test_chat_auth_disabled_by_default(client, monkeypatch):
    """Verify when REQUIRE_API_KEY is not set or false, requests pass without X-API-Key."""
    monkeypatch.setenv("REQUIRE_API_KEY", "false")
    response = client.post("/api/chat", json={"message": "Hello"})
    assert response.status_code == 200


def test_chat_auth_enforced_missing_key(client, monkeypatch):
    """Verify when REQUIRE_API_KEY=true, missing X-API-Key returns 401."""
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "secret-test-key")
    response = client.post("/api/chat", json={"message": "Hello"})
    assert response.status_code == 401
    assert "Invalid or missing API key" in response.json()["detail"]


def test_chat_auth_enforced_invalid_key(client, monkeypatch):
    """Verify when REQUIRE_API_KEY=true, wrong X-API-Key returns 401."""
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "secret-test-key")
    response = client.post(
        "/api/chat",
        headers={"X-API-Key": "wrong-key"},
        json={"message": "Hello"},
    )
    assert response.status_code == 401


def test_chat_auth_enforced_valid_key(client, monkeypatch):
    """Verify when REQUIRE_API_KEY=true, correct X-API-Key succeeds with 200."""
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "secret-test-key")
    response = client.post(
        "/api/chat",
        headers={"X-API-Key": "secret-test-key"},
        json={"message": "Hello"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# 5. Multi-Turn Session Continuity
# ---------------------------------------------------------------------------

def test_chat_multi_turn_session(client):
    """Verify sending multiple turns with the same session_id maintains session integrity."""
    session_id = "multi-turn-test-session"

    # Turn 1
    resp1 = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "My G1 router has a flashing red light"},
    )
    assert resp1.status_code == 200
    assert resp1.json()["session_id"] == session_id

    # Turn 2
    resp2 = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "I already rebooted it twice"},
    )
    assert resp2.status_code == 200
    assert resp2.json()["session_id"] == session_id


# ---------------------------------------------------------------------------
# 6. CORS Configuration Tests
# ---------------------------------------------------------------------------

def test_cors_headers_on_preflight(client):
    """Verify preflight OPTIONS requests return valid CORS headers."""
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type,X-API-Key",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers


# ---------------------------------------------------------------------------
# 7. Orchestrator Mocking & Exception Tests
# ---------------------------------------------------------------------------

def test_chat_with_mocked_orchestrator(client):
    """Verify API correctly formats mocked orchestrator envelope."""
    mock_envelope = ResponseEnvelope(
        response="Custom mock response text.",
        citations=[Citation(source_id="mock-doc", locator="section-1")],
        action=ActionEnum.INSTRUCT,
    )

    with patch("backend.main.orchestrator.process_turn", return_value=mock_envelope):
        response = client.post(
            "/api/chat",
            json={"session_id": "mock-sess", "message": "Trigger mock"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Custom mock response text."
        assert data["action"] == "instruct"
        assert len(data["citations"]) == 1
        assert data["citations"][0]["source_id"] == "mock-doc"


def test_chat_orchestrator_failure_returns_500(client):
    """Verify unhandled orchestrator exceptions are caught and return structured 500 error."""
    with patch("backend.main.orchestrator.process_turn", side_effect=RuntimeError("Database query failed")):
        response = client.post(
            "/api/chat",
            json={"session_id": "err-sess", "message": "Trigger failure"},
        )
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "Orchestrator processing failed" in data["detail"]


# ---------------------------------------------------------------------------
# 8. OpenAPI Documentation Endpoints
# ---------------------------------------------------------------------------

def test_openapi_json_and_docs_endpoints(client):
    """Verify OpenAPI schema and Swagger docs endpoints are live and correct."""
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200
    assert "swagger" in docs_resp.text.lower() or "html" in docs_resp.headers.get("content-type", "").lower()

    schema_resp = client.get("/openapi.json")
    assert schema_resp.status_code == 200
    schema = schema_resp.json()
    assert "openapi" in schema
    assert "/api/chat" in schema["paths"]
    assert "/api/health" in schema["paths"]
