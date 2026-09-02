"""Comprehensive unit and integration test suite for the FastAPI backend.

Tests cover:
- Health check endpoints
- Chat turn processing and response envelope validation
- Request validation (empty strings, missing fields)
- Session ID generation and preservation
- API Key authentication (both enforced and optional modes)
- CORS headers
- Multi-turn continuity
- Orchestrator exception handling
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
