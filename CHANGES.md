# Changelog

## [2026-09-04]

### Fixed
- **Security & Authentication Hardening (`backend/main.py`)**:
  - Replaced wildcard `*` CORS credentials with explicit local frontend origins (`localhost:5173`, `127.0.0.1:5173`, `localhost:3000`, `localhost:80`, `127.0.0.1:80`) and dynamic credential disabling on wildcard origins to comply with Fetch CORS specifications.
  - Removed default fallback API key `"orbitmesh-secret-key"`; enforced error logging and HTTP 500 when `REQUIRE_API_KEY=true` but no key is configured in the environment.
  - Sanitized HTTP 500 error responses to `"Orchestrator processing failed"` while preserving full server-side trace logging with `logger.error(..., exc_info=True)` to prevent internal information leakage.
- **Concurrency & Thread Safety (`src/agent/orchestrator.py`, `src/rag/llm.py`, `src/state/session.py`)**:
  - Replaced direct instance mutation of `last_retrieved_chunks` and `last_raw_envelope` in `OrbitMeshOrchestrator` with `threading.local()` properties to isolate per-request retrieval state across concurrent FastAPI worker threads.
  - Added a `threading.Lock()` to `LLMClient` protecting rate-limit buffer checks and `last_call_time` updates to avoid race conditions against external model providers.
  - Implemented `psycopg2.pool.ThreadedConnectionPool` in `SessionStateManager` for PostgreSQL connection reuse and thread safety.
  - Added `_init_lock` to prevent concurrent database schema initialization races.
  - Implemented automatic fallback to SQLite upon any PostgreSQL connection or query failure to prevent session state loss.
  - Configured SQLite connection timeout to 30.0 seconds to prevent database locking errors under concurrent workloads.
- **Container Infrastructure & Nginx Resolution (`frontend/nginx.conf`, `docker-compose.yml`, `backend/start_all.sh`)**:
  - Configured Docker DNS resolver (`resolver 127.0.0.11 valid=30s ipv6=off;`) and dynamic upstream variable (`set $backend_upstream "http://backend:8000";`) in `frontend/nginx.conf` to prevent Nginx startup crashes when the backend container starts asynchronously.
  - Added `backend` and `frontend` service definitions to `docker-compose.yml` to allow full stack container orchestration on a shared network.
  - Scoped container startup in `backend/start_all.sh` to `qdrant postgres adminer` to prevent port 8000 conflicts with the local Uvicorn development server.

## [2026-09-03]

### Added
- **Orchestrator End-to-End Test Suite (`tests/test_orchestrator.py`, `docs/testing.md`)**:
  - Created a dedicated 13-test suite verifying the complete multi-turn state machine in `OrbitMeshOrchestrator`.
  - Added test coverage for hardware hazard short-circuit escalation, prompt injection containment, model slot filling, factory reset confirmation/cancellation flows (Pro vs Standard), diagnostic RAG grounding and citation repairs, 4-turn/8-message dialogue window capping, resolution state tracking, sensitive info solicitation interception, archived documentation retrieval flags, and diagnostic step classification (`cable_checked`, `power_cycled`, `distance_checked`).
  - Added Section 4 Orchestrator Test Case Matrix to `docs/testing.md`.
- **Backend API Test Suite Expansion (`tests/test_backend_api.py`, `backend/main.py`)**:
  - Added structured try-except exception handling in `backend/main.py` returning HTTP 500 JSON errors for unexpected orchestrator failures.
  - Expanded test suite from 13 to 21 test cases covering whitespace session IDs, non-string type errors, malformed JSON bodies, Unicode/special characters, large payloads (>5000 chars), ActionEnum mapping variants, orchestrator exception containment, and OpenAPI/docs endpoint health.
  - Updated `docs/testing.md` test matrix with all new backend test scenarios and expected outcomes.
- **Frontend Test Suite Expansion (`frontend/src/__tests__/App.test.jsx`, `docs/testing.md`)**:
  - Expanded frontend unit test suite from 6 to 13 test cases using Vitest and React Testing Library.
  - Added keyboard interaction tests for Enter submission and Shift+Enter multi-line retention.
  - Added form validation tests for Send button disabled state on empty/whitespace input and in-flight request locking.
  - Added session management tests for multi-conversation switching and deletion from the sidebar.
  - Added storage persistence hydration test verifying existing sessions load from localStorage on mount.
  - Updated `docs/testing.md` test case matrix with specifications for all 7 new test scenarios.
### Changed
- **Evaluation Benchmark Rigor & Metric Corrections (`eval/runner.py`, `eval/cases.jsonl`, `src/agent/orchestrator.py`)**:
  - Reset `last_retrieved_chunks` at turn start in `OrbitMeshOrchestrator` to prevent stale chunks leaking into guardrail or early-exit turns.
  - Added `last_raw_envelope` capture in `OrbitMeshOrchestrator` to evaluate raw LLM citation generation independently of post-processing backfill repairs.
  - Eliminated permissive multi-label actions (e.g. `["instruct", "ask"]`) in `eval/cases.jsonl`, replacing each turn with a strict single ground-truth action.
  - Cleared `expected_source: []` on turns where retrieval is bypassed by design (hazard emergencies, prompt injection, resolution gratitude) so they are excluded from the retrieval denominator rather than counted as retrieval misses.
  - Updated `eval/runner.py` to enforce `turn_passed = action_match and citation_match and guardrail_match and retrieval_match`, ensuring turns cannot pass if retrieval fails.
  - Added Raw LLM Citation Accuracy alongside Final Repaired Citation Accuracy in evaluation summary metrics.
  - Curated evaluation cases from 20 down to 10 representative cases (14 turns total, reducing live LLM API calls from ~32 to ~10) to avoid API rate limiting on public model tiers while maintaining 100% coverage across core capabilities.
  - Documented Evaluation Benchmark Suite in `docs/testing.md` Section 5.
  - Updated Section 4 Observed Failures, Root Causes & Remediations in `docs/design_notes.md` detailing HTTP 429 rate limit pacing, guardrail retrieval isolation, and strict single-action protocol alignment.
- **PostgreSQL Session Storage (`src/state/session.py`, `scripts/init_db.py`)**:
  - Implemented PostgreSQL session storage support via `psycopg2` in `SessionStateManager`, controlled by `DB_BACKEND=postgres` and `DATABASE_URL`.
  - Added automatic table schema creation (`sessions` table) with dual PostgreSQL/SQLite query compatibility and graceful fallback.
  - Added `scripts/init_db.py` and `scripts/init_db.sh` for explicit database initialization and inspection.
- **Server-Side Hybrid Retrieval & Dynamic Calibration (`src/rag/`, `src/ingestion/`)**:
  - Migrated Qdrant knowledge collection to named dense vectors (`BAAI/bge-small-en-v1.5`) and sparse BM25 vectors (`Qdrant/bm25` via FastEmbed).
  - Moved RRF fusion and per-track score thresholding to the Qdrant server using `query_points` with `prefetch` and `models.FusionQuery(fusion=models.Fusion.RRF)`.
  - Added automated dynamic calibration during corpus ingestion in `VectorIndexer.calibrate_thresholds()`: probes in-domain vs out-of-domain separation margins and persists dynamic `calibrated_dense_floor` and `calibrated_sparse_floor` in collection metadata.
  - Updated `HybridRetriever` to dynamically read calibrated score floors from Qdrant metadata on startup.
- **Backend Automation (`backend/start_all.sh`)**:
  - Added automated, conditional Qdrant knowledge corpus ingestion on startup. The script checks Qdrant collection point count: runs `scripts/ingest.sh` if empty/uninitialized, and skips ingestion immediately if already populated.

## [2026-09-02]

### Added
- **Backend Service (`backend/`)**:
  - FastAPI service wrapping the OrbitMesh orchestrator (`POST /api/chat`, `GET /api/health`).
  - Container infrastructure via `docker-compose.yml` for PostgreSQL, Qdrant server, and Adminer web UI.
  - Startup scripts (`start_all.sh`, `start_api.sh`, `start_postgres.sh`, `start_qdrant.sh`).
  - Containerization with `backend/Dockerfile` and Amazon ECR push script (`push_ecr.sh`).
  - Documentation for local execution and AWS ECS Fargate deployment in `backend/README.md`.

- **Frontend Application (`frontend/`)**:
  - Full-page responsive React chatbot interface built with Vite.
  - Multi-stage production `frontend/Dockerfile` with Nginx and Amazon ECR push script (`push_ecr.sh`).
  - AWS Amplify deployment instructions in `frontend/README.md`.

- **Testing & Documentation (`tests/`, `docs/`)**:
  - Automated FastAPI backend test suite in `tests/test_backend_api.py` achieving 92% code coverage.
  - Automated React frontend component test suite in `frontend/src/__tests__/App.test.jsx` using Vitest and React Testing Library.
  - Unified test runner scripts `tests/run_backend_tests.sh` and `tests/run_frontend_tests.sh` with automated output logging to `logs/`.
  - Comprehensive testing architecture and test case matrix document in `docs/testing.md`.