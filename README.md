# OrbitMesh Support Assistant

For full technical architecture, chunking rationale, state design, and evaluation analysis, please refer to [`docs/design_notes.pdf`](docs/design_notes.pdf) (or [`docs/design_notes.md`](docs/design_notes.md)).

---

## Components Documentation

The project includes web application layers in addition to the core CLI orchestrator:

- **Frontend Application ([`frontend/`](frontend/))**:
  - Full-page responsive React chatbot user interface built with Vite.
  - Containerization with Docker and Nginx.
  - Deployment instructions for AWS Amplify.
  - *Full guide*: See [`frontend/README.md`](frontend/README.md).

- **Backend Service ([`backend/`](backend/))**:
  - FastAPI REST service exposing `POST /api/chat` and `GET /api/health`.
  - Supports PostgreSQL session storage, Qdrant vector database server, and Adminer web GUI.
  - Individual and all-in-one startup scripts (`start_all.sh`, `start_api.sh`, `start_postgres.sh`, `start_qdrant.sh`).
  - Containerization with Docker and Amazon ECR push script (`push_ecr.sh`).
  - Deployment architecture for AWS ECS Fargate and Amazon RDS.
  - *Full guide*: See [`backend/README.md`](backend/README.md).

- **Testing Guide ([`docs/testing.md`](docs/testing.md))**:
  - Comprehensive testing architecture, test case matrix, and code coverage documentation.
  - *Full guide*: See [`docs/testing.md`](docs/testing.md).

---

## Prerequisites & Installation

### 1. Environment Setup

Python 3.11 is required. Node.js 18+ is required for frontend development.

```bash
# Python environment
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
make setup
# Installs Python dependencies from requirements.txt
```

### 3. Configure Environment Variables (`.env`)

Copy `.env.example` to `.env` (or configure existing `.env`):

```bash
# LLM Configuration
LLM_MODE=openrouter                          # "openrouter" or "mock" (offline fallback)
OPENROUTER_API_KEY=your_openrouter_api_key   # Required if LLM_MODE=openrouter
OPENROUTER_MODEL=nvidia/nemotron-3.5-lightning:free
LLM_RATE_LIMIT_DELAY=1.0

# Vector Database (Qdrant)
# Set QDRANT_URL to use server mode; leave blank for local embedded storage in data/qdrant
QDRANT_URL=http://localhost:6333
QDRANT_PATH=data/qdrant

# Database (PostgreSQL or SQLite fallback)
DB_BACKEND=postgres                          # "postgres" or "sqlite"
DATABASE_URL=postgresql://orbitmesh:orbitmesh@localhost:5432/orbitmesh
SQLITE_DB_PATH=data/sessions.db
```

---

## Building & Ingesting the Corpus

Index the Markdown documentation from `corpus/` into the vector database:

```bash
make ingest
# or: ./scripts/ingest.sh
```

*Note*: If using Qdrant server mode (`QDRANT_URL=http://localhost:6333`), start the Qdrant container before running ingestion (`./backend/start_qdrant.sh`). Indexed vectors persist in the `qdrant_data` volume across restarts.

---

## Running the Application

### 1. Web Application (Full Stack)

1. **Start Backend Services**:
   ```bash
   ./backend/start_all.sh
   ```
   Starts PostgreSQL (`localhost:5432`), Qdrant (`localhost:6333`), Adminer (`localhost:8080`), and the FastAPI server (`localhost:8000`).

2. **Start Frontend Dev Server**:
   ```bash
   ./frontend/start.sh
   ```
   Launches the React application at `http://localhost:5173`.

### 2. Interactive Terminal Chat
Start an interactive terminal troubleshooting session:

```bash
make chat
# or: ./scripts/chat.sh
```

### 3. JSONL Streaming Adapter
Run the newline-delimited JSON interface over `stdin` and `stdout`:

```bash
./scripts/chat.sh --jsonl
```

**Example Input (stdin)**:
```json
{"session_id": "case-1", "message": "My N1 satellite node has a solid amber light"}
```

**Example Output (stdout)**:
```json
{
  "response": "A solid amber LED on your satellite N1 node indicates it is offline or out of range. Please move the N1 node closer to the main router.",
  "citations": [
    {"source_id": "led-reference", "locator": "N1 node LEDs"}
  ],
  "action": "instruct"
}
```

---

## Verification & Testing

### 1. Backend API Test Suite
Runs unit and integration tests for the FastAPI service with code coverage and automatic logging to `logs/`:

```bash
./tests/run_backend_tests.sh
```

### 2. Full Test Suite
Runs all unit and integration tests across session state, guardrails, retrieval, and API endpoints:

```bash
make test
# or: pytest
```

### 3. Verify JSONL Transport Contract
Verifies that `./scripts/chat.sh --jsonl` conforms strictly to the protocol without leaking diagnostic text to `stdout`:

```bash
python scripts/check_contract.py
```

### 4. Run Benchmark Evaluation
Runs the evaluation benchmark cases and outputs quantified retrieval and generation accuracy metrics:

```bash
make eval
# or: python eval/runner.py
```

For the complete testing strategy and test case matrix, see [`docs/testing.md`](docs/testing.md).

---

## Project Structure

```
.
├── backend/                 # FastAPI REST API, Dockerfile, and AWS ECS guide
│   ├── main.py              # Application endpoints (/api/chat, /api/health)
│   ├── Dockerfile           # Backend container build
│   ├── push_ecr.sh          # ECR build and push script
│   ├── start_all.sh         # All-in-one backend stack starter
│   ├── start_api.sh         # FastAPI uvicorn starter
│   ├── start_postgres.sh    # PostgreSQL + Adminer starter
│   ├── start_qdrant.sh      # Qdrant vector server starter
│   └── README.md            # Backend documentation & AWS deployment
├── corpus/                  # OrbitMesh documentation and manifest.json
├── data/                    # Local SQLite (sessions.db) and Qdrant storage
├── docs/
│   ├── Diagram.jpg          # System architecture diagram
│   ├── design_notes.md      # Technical design notes
│   ├── design_notes.pdf     # PDF version of design notes
│   └── testing.md           # Comprehensive testing documentation
├── eval/
│   ├── cases.jsonl          # Evaluation benchmark cases
│   └── runner.py            # Evaluation metrics benchmark runner
├── frontend/                # React + Vite chatbot user interface
│   ├── src/                 # Chat components, API client, and styles
│   ├── Dockerfile           # Multi-stage Nginx container build
│   ├── push_ecr.sh          # Frontend ECR push script
│   ├── start.sh             # Vite dev server startup script
│   └── README.md            # Frontend documentation & Amplify deployment
├── logs/                    # Runtime logs and test execution logs
├── scripts/
│   ├── chat.sh              # Entry point script (interactive or --jsonl)
│   ├── check_contract.py    # Transport contract verification tool
│   └── ingest.sh            # Ingestion script
├── src/
│   ├── agent/               # Orchestrator coordinating retrieval, state, & LLM
│   ├── cli/                 # Interactive and JSONL CLI interfaces
│   ├── core/                # Models, config, and stderr logging
│   ├── guardrails/          # Input (PII/injection) and output (hazard/reset) guards
│   ├── ingestion/           # Markdown parser and Qdrant indexer
│   ├── rag/                 # FastEmbed embeddings, hybrid retriever, and LLM client
│   └── state/               # Database-backed session and memory manager
├── tests/                   # Test suites (backend API, state, guardrails, retrieval)
│   ├── run_backend_tests.sh # Backend test runner with coverage and logging
│   └── test_backend_api.py  # FastAPI endpoint tests
├── docker-compose.yml       # Local infrastructure (Qdrant, PostgreSQL, Adminer)
├── Makefile                 # Standard automation targets
├── requirements.txt         # Project dependencies
└── README.md                # Project overview and quick start
```
