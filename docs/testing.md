# Comprehensive Testing Guide

This document outlines the testing architecture, methodology, test matrix, and execution procedures for the OrbitMesh Support Assistant system.

---

## 1. Testing Architecture & Isolation

All automated tests adhere to strict operational guarantees:
- **Zero Token Cost / Offline Execution**: `LLM_MODE=mock` is forced across test suites. Calls never contact OpenRouter or consume API credits.
- **Filesystem Isolation**: File paths (SQLite database, Qdrant vectors, log files) are redirected to isolated temporary directories (`tempfile.mkdtemp`), preventing interference with local development data (`data/`).
- **In-Memory Testing**: The FastAPI backend is tested using Starlette/FastAPI's in-memory `TestClient` without requiring network binding or external daemon processes.

---

## 2. Backend API Test Suite

The backend test suite is located in `tests/test_backend_api.py` and targets `backend/main.py`.

### 2.1 Test Execution

Run the backend test suite using the dedicated runner script:
```bash
./tests/run_backend_tests.sh
```
Test results are printed to the console and automatically saved to a timestamped log file in `logs/` (e.g., `logs/backend_test_YYYYMMDD_HHMMSS.log`).

Or run via pytest directly:
```bash
LLM_MODE=mock pytest tests/test_backend_api.py -v --cov=backend --cov-report=term-missing
```

To run a specific test by name:
```bash
./tests/run_backend_tests.sh -k "test_chat_auth"
```

---

### 2.2 Test Case Matrix

| Test Function | Target Endpoint | Test Scenario | Expected Outcome | Category |
|---|---|---|---|---|
| `test_health_check_returns_ok` | `GET /api/health` | Service liveness probe | `200 OK`, JSON `{"status": "ok", "service": "orbitmesh-backend", ...}` | Liveness / Monitoring |
| `test_chat_missing_message_fails_validation` | `POST /api/chat` | Request payload `{}` without `message` | `422 Unprocessable Entity` | Schema Validation |
| `test_chat_empty_message_fails_validation` | `POST /api/chat` | Request payload `{"message": ""}` | `422 Unprocessable Entity` | Schema Validation |
| `test_chat_auto_generates_session_id` | `POST /api/chat` | Request omitting `session_id` | `200 OK`, generated `session_id` starts with `web-` | State Management |
| `test_chat_preserves_provided_session_id` | `POST /api/chat` | Request supplying explicit `session_id` | `200 OK`, response matches input `session_id` | State Management |
| `test_chat_response_structure_and_types` | `POST /api/chat` | Complete turn request with query | `200 OK`, contains non-empty `response`, `action`, and list of `citations` | Contract Verification |
| `test_chat_auth_disabled_by_default` | `POST /api/chat` | `REQUIRE_API_KEY=false`, request without header | `200 OK`, request allowed for public web demo | Security / Auth |
| `test_chat_auth_enforced_missing_key` | `POST /api/chat` | `REQUIRE_API_KEY=true`, request without header | `401 Unauthorized`, error detail returned | Security / Auth |
| `test_chat_auth_enforced_invalid_key` | `POST /api/chat` | `REQUIRE_API_KEY=true`, wrong `X-API-Key` | `401 Unauthorized`, error detail returned | Security / Auth |
| `test_chat_auth_enforced_valid_key` | `POST /api/chat` | `REQUIRE_API_KEY=true`, valid `X-API-Key` | `200 OK`, request processed | Security / Auth |
| `test_chat_multi_turn_session` | `POST /api/chat` | Sequential turns with same `session_id` | `200 OK` on all turns, session continuity maintained | Multi-turn State |
| `test_cors_headers_on_preflight` | `OPTIONS /api/chat` | Cross-origin preflight request | `200 OK`, `access-control-allow-origin` header present | Network / CORS |
| `test_chat_with_mocked_orchestrator` | `POST /api/chat` | Unit test with mocked orchestrator return | `200 OK`, properly maps `ResponseEnvelope` to `ChatResponse` | Unit Isolation |

---

### 2.3 Expected Code Coverage

Target coverage for `backend/main.py`:
- **Line Coverage**: > 90%
- **Branch Coverage**: 100% of authentication paths (`REQUIRE_API_KEY` enabled vs disabled).
- **Endpoint Coverage**: 100% of defined HTTP routes (`GET /api/health`, `POST /api/chat`, `OPTIONS /api/chat`).

---

## 3. Future Test Suites (Roadmap)

The following suites will be added to this guide in subsequent phases:
- **Frontend Test Suite**: Component rendering, session storage persistence, API error state banners, and chat bubble styling.
- **Orchestrator Logic Suite**: Multi-turn slot filling, factory reset confirmation, hardware hazard escalation, and prompt injection rejection.
- **Transport Contract Suite**: Strict JSONL stdin/stdout serialization and stderr log isolation verification.
