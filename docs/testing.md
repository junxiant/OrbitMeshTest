# Comprehensive Testing Guide

This document outlines the testing architecture, methodology, test matrix, and execution procedures for the OrbitMesh Support Assistant system.

---

## 1. Testing Architecture & Isolation

All automated tests adhere to strict operational guarantees:
- **Zero Token Cost / Offline Execution**: `LLM_MODE=mock` is forced across test suites. Calls never contact OpenRouter or consume API credits.
- **Filesystem Isolation**: File paths (SQLite database, Qdrant vectors, log files) are redirected to isolated temporary directories (`tempfile.mkdtemp`), preventing interference with local development data (`data/`).
- **In-Memory Backend Testing**: The FastAPI backend is tested using Starlette/FastAPI's in-memory `TestClient` without requiring network binding or external daemon processes.
- **Headless Frontend Testing**: The React frontend is tested using Vitest and React Testing Library in a headless `jsdom` environment with mocked network API calls.

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
| `test_chat_whitespace_session_id_auto_generates_id` | `POST /api/chat` | Request with whitespace-only `session_id` | `200 OK`, generates clean `web-` prefixed session ID | State Management |
| `test_chat_non_string_types_fail_validation` | `POST /api/chat` | Non-string message payload (integer, list) | `422 Unprocessable Entity` | Schema Validation |
| `test_chat_malformed_json_body` | `POST /api/chat` | Broken/invalid JSON string body | `400` / `422 Unprocessable Entity` | Robustness / Input |
| `test_chat_unicode_and_special_characters` | `POST /api/chat` | Multilingual Unicode, accents, symbols | `200 OK`, handles unicode without encoding faults | Internationalization |
| `test_chat_large_message_payload` | `POST /api/chat` | Very large input payload (>5,000 chars) | `200 OK`, processed without crashing or memory errors | Stress / Payload Limits |
| `test_chat_action_types_mapping` | `POST /api/chat` | Verifies `ActionEnum` (`ask`, `instruct`, `escalate`) mapping | `200 OK`, action strings properly formatted | Contract Verification |
| `test_chat_orchestrator_failure_returns_500` | `POST /api/chat` | Orchestrator internal unhandled exception | `500 Internal Server Error`, structured error detail | Error Containment |
| `test_openapi_json_and_docs_endpoints` | `GET /docs`, `GET /openapi.json` | Swagger UI and OpenAPI schema liveness | `200 OK`, OpenAPI JSON contains defined endpoints | API Documentation |

---

### 2.3 Expected Code Coverage

Target coverage for `backend/main.py`:
- **Line Coverage**: > 90%
- **Branch Coverage**: 100% of authentication paths (`REQUIRE_API_KEY` enabled vs disabled).
- **Endpoint Coverage**: 100% of defined HTTP routes (`GET /api/health`, `POST /api/chat`, `OPTIONS /api/chat`).

---

## 3. Frontend Test Suite

The frontend test suite is located in `frontend/src/__tests__/App.test.jsx` and verifies the React UI components, user interactions, and state management.

### 3.1 Test Architecture & Tooling
- **Test Runner**: Vitest (fast, Vite-native testing framework).
- **DOM Simulation**: `jsdom` (in-memory headless browser environment).
- **Component Testing**: React Testing Library (`@testing-library/react` and `@testing-library/jest-dom`).
- **Network Isolation**: All backend API calls (`api.sendMessage`) are mocked via Vitest spies (`vi.spyOn`), ensuring 100% offline, deterministic tests that do not depend on the backend server being active.

---

### 3.2 Test Execution

Run the frontend test suite using the unified runner script:
```bash
./tests/run_frontend_tests.sh
```
Test results are printed to the console and automatically saved to a timestamped log file in `logs/` (e.g., `logs/frontend_test_YYYYMMDD_HHMMSS.log`).

Alternatively, execute within the frontend directory:
```bash
cd frontend && npm test
```

---

### 3.3 Test Case Matrix

| Test Case | Target Component | User Action / Event | Expected Outcome | Category |
|---|---|---|---|---|
| `renders the chatbot interface with initial welcome state` | `App.jsx` | Initial mount | Header, welcome greeting, input box, and Send button render | Component Rendering |
| `sends query directly when a suggestion chip is clicked` | `App.jsx` | User clicks quick query chip | User message bubble appears and assistant reply displays | User Interaction / Async |
| `displays user message and assistant reply with action and citations` | `App.jsx` | User types query and submits | Message bubble appears immediately; assistant reply, action badge, and citations display | Async Chat Flow |
| `displays an error message when the API request fails` | `App.jsx` | API network error simulated | User-friendly error banner renders gracefully without crashing | Error Handling |
| `toggles sidebar collapse state when sidebar button is clicked` | `App.jsx` | User clicks toggle icon | Sidebar transitions between expanded and collapsed mini-rail | UI Navigation |
| `clears active conversation and starts a new session on New Chat click` | `App.jsx` | User clicks "+ New Chat" | Active messages clear, fresh session generated, welcome screen returns | Session Management |
| `submits query when Enter key is pressed without Shift` | `App.jsx` | User presses Enter in input textarea | Submits message, calls `sendMessage`, renders assistant reply | Keyboard Accessibility |
| `does not submit query when Shift+Enter is pressed` | `App.jsx` | User presses Shift+Enter in input textarea | Preserves multi-line draft text without triggering API submission | Keyboard Accessibility |
| `disables send button when input is empty or whitespace-only` | `App.jsx` | Empty or whitespace input string | Send button disabled state enforced | Form Validation |
| `disables input and send button while request is in flight` | `App.jsx` | API request pending resolution | Input and Send button disabled, preventing duplicate submissions | Async Concurrency |
| `switches between multiple conversations in sidebar` | `App.jsx` | User clicks past session in sidebar | Active session switches, displaying correct conversational context | Session Management |
| `deletes a conversation from the sidebar` | `App.jsx` | User clicks trash delete icon on session item | Targeted session removed from sidebar list and state | Session Management |
| `loads existing sessions from localStorage on initial mount` | `App.jsx` | Initial render with populated `orbitmesh_chat_sessions` | Pre-existing chat history and session titles hydrated from localStorage | Storage Persistence |

---

## 4. Orchestrator End-to-End Test Suite

The orchestrator test suite is located in `tests/test_orchestrator.py` and targets `src/agent/orchestrator.py`.

### 4.1 Test Execution

Run via pytest:
```bash
LLM_MODE=mock pytest tests/test_orchestrator.py -v
```

### 4.2 Test Case Matrix

| Test Function | Target Component | Test Scenario | Expected Outcome | Category |
|---|---|---|---|---|
| `test_hardware_hazard_escalation_short_circuit` | `OrbitMeshOrchestrator` | Smoke, fire, sparks, or thermal emergency query | `ActionEnum.ESCALATE`, `is_escalated = True`, immediate short-circuit | Safety & Escalation |
| `test_prompt_injection_containment` | `OrbitMeshOrchestrator` | Adversarial system prompt override instruction | `ActionEnum.ASK`, refusal canned response, no prompt leaks | Security Guardrails |
| `test_model_identification_slot_filling` | `OrbitMeshOrchestrator` | Progressive mentions of Pro gateway, R1 router, N1 node | `session.identified_model` dynamically updated in session state | Slot-Filling |
| `test_factory_reset_warning_and_cancellation` | `OrbitMeshOrchestrator` | Reset request followed by "no / cancel" response | Issues warning on Turn 1; clears pending state and suggests non-destructive alternative on Turn 2 | Multi-Turn State Machine |
| `test_factory_reset_confirmation_standard_model` | `OrbitMeshOrchestrator` | R1/N1 reset request followed by "yes / proceed" | Returns standard 15-second reset step citing `reset-recovery-guide`; records `factory_reset` step | Multi-Turn State Machine |
| `test_factory_reset_confirmation_pro_model` | `OrbitMeshOrchestrator` | Pro reset request followed by "yes / confirm" | Returns Pro 10-second reset pin step citing `pro-quick-start-guide` | Multi-Turn State Machine |
| `test_factory_reset_ask_alternatives` | `OrbitMeshOrchestrator` | Inquiry for alternatives before resetting | Intercepts with power cycling and pairing reset recommendations without wiping | Multi-Turn State Machine |
| `test_rag_end_to_end_diagnostic_turn` | `OrbitMeshOrchestrator` | In-domain diagnostic query ("N1 solid amber") | Retrieves grounded chunks, validates/repairs citations, sets `INSTRUCT` or `ASK` | RAG End-to-End |
| `test_multi_turn_dialogue_window_capping` | `OrbitMeshOrchestrator` | 6 sequential conversation turns in single session | Dialogue window capped at 4 turns (8 messages); turns 1–2 discarded from window | Memory & Windowing |
| `test_resolution_state_tracking` | `OrbitMeshOrchestrator` | Turn resulting in `ActionEnum.RESOLVED` | `session.is_resolved = True` persisted to database | State Management |
| `test_sensitive_info_solicitation_intercepted` | `OrbitMeshOrchestrator` | LLM response attempting to solicit credit card / passwords | Output guardrail sanitizes and scrubs sensitive solicitation | Output Guardrails |
| `test_archived_documentation_retrieval_flag` | `OrbitMeshOrchestrator` | Query mentioning "archive" or "superseded" | Passes `include_archived=True` to retriever to search legacy versions | Knowledge Retrieval |
| `test_diagnostic_step_classification` | `OrbitMeshOrchestrator` | Responses with cable, power cycle, or distance steps | Correctly appends `cable_checked`, `power_cycled`, or `distance_checked` to `session.attempted_steps` | Diagnostic Tracking |

---

## 5. Evaluation Benchmark Suite

The evaluation benchmark is located in `eval/runner.py` and evaluates end-to-end performance against curated golden test cases in `eval/cases.jsonl`.

### 5.1 Test Execution

Run the evaluation benchmark:
```bash
python eval/runner.py
```
Outputs are printed to the console and automatically persisted to `eval_results/` as timestamped JSON and Markdown reports (e.g. `eval_results/latest.json`).

### 5.2 Curated Benchmark Matrix (10 Cases, 14 Turns)

The benchmark is optimized to 14 turns (~10 live LLM API calls) to prevent API rate limits on public tiers while verifying 100% of core assistant capabilities:

| Case ID | Turns | Test Scenario | Expected Action | Expected Sources | Category |
|---|---|---|---|---|---|
| `case-01-diagnostic-n1-led` | 1 | N1 solid amber light | `instruct` | `led-reference`, `troubleshooting-guide` | RAG Diagnostic |
| `case-02-pro-gateway-setup` | 1 | R5 Pro gateway setup & product-line filter | `instruct` | `pro-quick-start-guide`, `pro-led-reference` | Model Filtering |
| `case-03-hardware-hazard` | 1 | Sparks and burning smell from power port | `escalate` | *(Bypassed)* | Safety Escalation |
| `case-04-casing-disassembly` | 1 | Router casing disassembly inquiry | `escalate` | *(Bypassed)* | Policy Enforcement |
| `case-05-prompt-injection` | 1 | System prompt override and leak attempt | `ask` | *(Bypassed)* | Security Guardrails |
| `case-06-pii-scrubbing` | 1 | User passes plaintext password in message | `ask` | *(Bypassed)* | PII Redaction |
| `case-07-unsupported-firmware` | 1 | Flashing custom OpenWrt firmware inquiry | `escalate` | `warranty-safety-policy` | Unsupported Action |
| `case-08-informal-clarification`| 1 | Broken grammar / slang query | `ask` | *(Bypassed)* | Clarification Slot-Filling |
| `case-09-factory-reset-flow` | 2 | Turn 1: Reset inquiry (warning)<br>Turn 2: Explicit user consent (execution) | Turn 1: `ask`<br>Turn 2: `instruct` | Turn 1: *(Bypassed)*<br>Turn 2: `reset-recovery-guide` | Multi-Turn Consent |
| `case-10-diagnostic-resolution`| 4 | Turn 1: Initial R1 setup inquiry<br>Turn 2: Solid amber symptom<br>Turn 3: Blue WAN cable step<br>Turn 4: Confirmation & gratitude | Turns 1–3: `instruct`<br>Turn 4: `resolved` | Turns 1–3: `quick-start-guide`, `led-reference`<br>Turn 4: *(Bypassed)* | Multi-Turn Journey to Resolution |

---

## 6. Transport Contract Suite (Roadmap)

- **Transport Contract Suite**: Strict JSONL stdin/stdout serialization and stderr log isolation verification (`tests/test_contract.py`).
