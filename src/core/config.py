import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_DIR = PROJECT_ROOT / 'corpus'
MANIFEST_PATH = CORPUS_DIR / 'manifest.json'
DATA_DIR = PROJECT_ROOT / 'data'
QDRANT_STORAGE_DIR = Path(os.getenv('QDRANT_PATH', str(DATA_DIR / 'qdrant')))
QDRANT_PATH = QDRANT_STORAGE_DIR

# SESSIONS_DB_PATH is the canonical override; SQLITE_DB_PATH is kept for backward compatibility.
SQLITE_DB_PATH = Path(
    os.getenv('SESSIONS_DB_PATH') or os.getenv('SQLITE_DB_PATH') or str(DATA_DIR / 'sessions.db')
)
SESSIONS_DB_PATH = SQLITE_DB_PATH

DB_BACKEND = os.getenv('DB_BACKEND', 'sqlite').lower().strip()
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()

LOGS_DIR = Path(os.getenv('LOGS_DIR', str(PROJECT_ROOT / 'logs')))
LOG_FILE_PATH = Path(os.getenv('LOG_FILE_PATH', str(LOGS_DIR / 'app.log')))
EVAL_RESULTS_DIR = Path(os.getenv('EVAL_RESULTS_DIR', str(PROJECT_ROOT / 'eval_results')))

QDRANT_URL = os.getenv('QDRANT_URL', '')

OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY', '')

# Valid LLM modes: mock (deterministic offline), live (OpenRouter), replay (cached
# fixtures), record (live + capture fixtures). Legacy value 'openrouter' maps to 'live'.
VALID_LLM_MODES = frozenset({'mock', 'live', 'replay', 'record'})
_raw_llm_mode = os.getenv('LLM_MODE', 'mock' if not OPENROUTER_API_KEY else 'live').lower().strip()
if _raw_llm_mode == 'openrouter':
    _raw_llm_mode = 'live'
if _raw_llm_mode not in VALID_LLM_MODES:
    raise ValueError(
        f"Invalid LLM_MODE '{_raw_llm_mode}'. Expected one of: {', '.join(sorted(VALID_LLM_MODES))}."
    )
LLM_MODE = _raw_llm_mode

OPENROUTER_MODEL = os.getenv('OPENROUTER_MODEL', 'nvidia/nemotron-3.5-lightning:free')
OPENROUTER_FALLBACK_MODELS = [
    OPENROUTER_MODEL,
    'liquid/lfm-2.5-2.6b:free',
    'z-ai/glm-5.2:free',
    'nvidia/nemotron-3-ultra-550b-a55b:free',
    'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free',

]

LLM_RATE_LIMIT_DELAY = float(os.getenv('LLM_RATE_LIMIT_DELAY', '1.0'))
EMBEDDING_MODEL_NAME = os.getenv('EMBEDDING_MODEL_NAME', 'BAAI/bge-small-en-v1.5')
EMBEDDING_DIMENSION = int(os.getenv('EMBEDDING_DIMENSION', '384'))
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

# Retrieval abstention floors (raw per-track scores, checked BEFORE rank fusion).
# Tuned empirically 2026-08-25 on the full 56-chunk corpus with bge-small-en-v1.5:
# in-domain best-dense-cosine min 0.687 / best-BM25 min 4.45; out-of-domain
# best-dense max 0.573 / best-BM25 max 0.00. Full per-query probe table in
# src/rag/retriever.py next to the gate.
# Higher - More strict. Lower - More lenient.
DENSE_SCORE_FLOOR = float(os.getenv('DENSE_SCORE_FLOOR', '0.62'))
BM25_SCORE_FLOOR = float(os.getenv('BM25_SCORE_FLOOR', '2.5'))


def ensure_dirs() -> None:
    """Create runtime directories.

    Deliberately NOT executed at import time: entrypoints that need writable
    directories (ingestion main, chat CLIs for sessions/logs, eval runner for
    results) call this explicitly, so merely importing config has no
    filesystem side effects.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QDRANT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    SQLITE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
