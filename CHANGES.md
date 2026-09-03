# Changelog

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