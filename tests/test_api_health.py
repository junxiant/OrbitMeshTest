"""Test suite for FastAPI health, liveness, and readiness probes.

Can be run via pytest:
    pytest tests/test_api_health.py

Or executed directly as a standalone test script:
    python tests/test_api_health.py
"""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint_metadata(client):
    """Verify GET /api/health returns 200 OK, service metadata, and dependency reports."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "orbitmesh-backend"
    assert "version" in data
    assert "dependencies" in data
    assert "database" in data["dependencies"]
    assert "vector_store" in data["dependencies"]


def test_liveness_probe_returns_alive(client):
    """Verify GET /api/health/live returns HTTP 200 with alive status."""
    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"


def test_readiness_probe_success(client):
    """Verify GET /api/health/ready returns HTTP 200 when all dependencies are healthy."""
    with patch("backend.main.check_database_health", return_value=(True, {"status": "connected"})):
        with patch("backend.main.check_qdrant_health", return_value=(True, {"status": "connected"})):
            resp = client.get("/api/health/ready")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ready"
            assert data["dependencies"]["database"]["status"] == "connected"
            assert data["dependencies"]["vector_store"]["status"] == "connected"


def test_readiness_probe_database_failure(client):
    """Verify GET /api/health/ready returns HTTP 503 when database is unhealthy."""
    with patch("backend.main.check_database_health", return_value=(False, {"status": "unhealthy", "error": "Connection refused"})):
        with patch("backend.main.check_qdrant_health", return_value=(True, {"status": "connected"})):
            resp = client.get("/api/health/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["dependencies"]["database"]["status"] == "unhealthy"


def test_readiness_probe_vector_store_failure(client):
    """Verify GET /api/health/ready returns HTTP 503 when Qdrant is unreachable."""
    with patch("backend.main.check_database_health", return_value=(True, {"status": "connected"})):
        with patch("backend.main.check_qdrant_health", return_value=(False, {"status": "unhealthy", "error": "Timeout"})):
            resp = client.get("/api/health/ready")
            assert resp.status_code == 503
            data = resp.json()
            assert data["status"] == "not_ready"
            assert data["dependencies"]["vector_store"]["status"] == "unhealthy"


if __name__ == "__main__":
    c = TestClient(app)
    print("Testing GET /api/health...")
    test_health_endpoint_metadata(c)
    print("Testing GET /api/health/live...")
    test_liveness_probe_returns_alive(c)
    print("Testing GET /api/health/ready (healthy)...")
    test_readiness_probe_success(c)
    print("Testing GET /api/health/ready (db failure -> 503)...")
    test_readiness_probe_database_failure(c)
    print("Testing GET /api/health/ready (qdrant failure -> 503)...")
    test_readiness_probe_vector_store_failure(c)
    print("All health and readiness probe checks passed successfully.")
