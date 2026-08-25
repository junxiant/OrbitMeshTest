# OrbitMesh Support Assistant

For full technical architecture, chunking rationale, state design, and evaluation analysis, please refer to [`docs/design_notes.pdf`](docs/design_notes.pdf) (or [`docs/design_notes.md`](docs/design_notes.md)).

---

## Architecture Overview

- **Offline Vector Ingestion**: Hierarchical Markdown chunking with SHA-256 deduplication and dense local embeddings via **FastEmbed** (`BAAI/bge-small-en-v1.5`), indexed into **Qdrant** (embedded or server).
- **Session State & Memory**: **SQLite** (`data/sessions.db`) tracking long-lived slots (`identified_model`, `attempted_steps`, `pending_confirmation`) across unlimited turns while bounding raw token context via a sliding window of the last $N$ turns.
- **Safety Guardrails**: Input PII/credential redaction, prompt injection filtering, mandatory factory reset confirmation warning, and immediate hardware hazard escalation.
- **Inference & Resilience**: OpenRouter LLM integration with automatic model fallback cascade and deterministic offline expert mode.
- **Strict Transport Contract**: Clean JSONL streaming interface with diagnostics isolated to `stderr`.

---

## Prerequisites & Installation

### 1. Environment Setup

Python 3.9+ is required. Activate your environment (e.g. Conda or venv):

```bash
conda create -n testing python=3.9
conda activate testing
# or: python3 -m venv venv && source venv/bin/activate
```

### 2. Install Dependencies

```bash
make setup
# or: pip install -r requirements.txt
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
# Leave QDRANT_URL blank to use local embedded storage in data/qdrant
QDRANT_URL=
QDRANT_PATH=data/qdrant

# SQLite Database
SQLITE_DB_PATH=data/sessions.db
```

---

## Building & Ingesting the Corpus

Index the Markdown documentation from `corpus/` into the Qdrant vector database:

```bash
make ingest
# ./scripts/ingest.sh
```

---

## Running the Application

### 1. Interactive Terminal Chat
Start an interactive troubleshooting session:

```bash
make chat
# ./scripts/chat.sh
```

### 2. JSONL Streaming Adapter
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

## Verification & Evaluation

### 1. Verify JSONL Transport Contract
Verifies that `./scripts/chat.sh --jsonl` conforms strictly to the protocol without leaking text to `stdout`:

```bash
python scripts/check_contract.py
```

### 2. Run Test Suite
Runs unit tests for session state, guardrails, and indexing:

```bash
make test
# pytest
```

### 3. Run Benchmark Evaluation
Runs the 16-case benchmark evaluation suite and outputs quantified quality metrics:

```bash
make eval
# python eval/runner.py
```

---

## Project Structure

```
.
├── corpus/                  # OrbitMesh documentation and manifest.json
├── data/                    # Local SQLite (sessions.db) and Qdrant storage
├── docs/
│   ├── Diagram.jpg          # System architecture diagram
│   ├── design_notes.md      # Technical design notes
│   └── design_notes.pdf     # PDF version of design notes
├── eval/
│   ├── cases.jsonl          # 16 multi-turn evaluation benchmark cases
│   └── runner.py            # Evaluation metrics benchmark runner
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
│   └── state/               # SQLite-backed session and memory manager
├── Makefile                 # Standard automation targets
├── requirements.txt         # Project dependencies
└── README.md               # User guide and run instructions
```
