"""Global test configuration: forced mock mode and filesystem isolation.

src.core.config reads the environment at import time, so the overrides below
must land BEFORE any test module imports anything from src. pytest imports
conftest.py ahead of collection, which makes module level assignment here the
earliest reliable hook (a fixture would run too late).

Guarantees for every test in the suite:
- LLM_MODE is forced to "mock": `make test` can never call OpenRouter or burn
  API credits, even with a real OPENROUTER_API_KEY sitting in .env
  (load_dotenv does not override variables already present in the process env).
- Every writable path (Qdrant storage, sessions DB, logs, eval results) is
  redirected to a session-unique temp directory, never the repo's data/,
  logs/ or eval_results/.
"""
import atexit
import os
import shutil
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# One scratch root per test session. Embedded Qdrant holds an exclusive lock
# per path, so this also keeps concurrent test runs from fighting over
# data/qdrant.
_TEST_ROOT = Path(tempfile.mkdtemp(prefix="orbitmesh-tests-"))

_FORCED_ENV: dict[str, str] = {
    # Belt-and-braces with `make test` (which also sets LLM_MODE=mock).
    "LLM_MODE": "mock",
    "OPENROUTER_API_KEY": "",
    "QDRANT_PATH": str(_TEST_ROOT / "qdrant"),
    # QDRANT_URL empty: never let tests talk to a remote/server instance.
    "QDRANT_URL": "",
    "DB_BACKEND": "sqlite",
    "DATABASE_URL": "",
    "SESSIONS_DB_PATH": str(_TEST_ROOT / "sessions.db"),
    "SQLITE_DB_PATH": str(_TEST_ROOT / "sessions.db"),  # legacy alias
    "LOGS_DIR": str(_TEST_ROOT / "logs"),
    "LOG_FILE_PATH": str(_TEST_ROOT / "logs" / "app.log"),
    "EVAL_RESULTS_DIR": str(_TEST_ROOT / "eval_results"),
}

for _key, _value in _FORCED_ENV.items():
    os.environ[_key] = _value


def _cleanup_test_root() -> None:
    # ignore_errors: embedded Qdrant may still hold file handles on Windows.
    shutil.rmtree(_TEST_ROOT, ignore_errors=True)


atexit.register(_cleanup_test_root)


@pytest.fixture(scope="session", autouse=True)
def isolated_test_environment() -> Iterator[None]:
    """Keep the forced env pinned for the whole session and verify config honored it.

    The real work happened at import time above; this fixture re-asserts the
    values (guarding against test code or .env reloading mutating them) and
    fails fast if src.core.config was somehow imported with different settings.
    """
    mp = pytest.MonkeyPatch()
    for key, value in _FORCED_ENV.items():
        mp.setenv(key, value)

    from src.core import config

    assert config.LLM_MODE == "mock", (
        "Tests must run in mock mode; src.core.config was imported before "
        "conftest.py forced the environment."
    )
    assert config.QDRANT_PATH == Path(_FORCED_ENV["QDRANT_PATH"])
    assert config.SESSIONS_DB_PATH == Path(_FORCED_ENV["SESSIONS_DB_PATH"])

    yield
    mp.undo()
