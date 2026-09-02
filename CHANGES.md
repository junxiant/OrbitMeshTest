# Changelog

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
  - Automated FastAPI test suite in `tests/test_backend_api.py`.
  - Test runner script `tests/run_backend_tests.sh` with automated logging to `logs/`.
  - Comprehensive testing architecture and test case matrix document in `docs/testing.md`.
