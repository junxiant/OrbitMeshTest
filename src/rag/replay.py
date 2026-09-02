from __future__ import annotations

import hashlib
import json
from pathlib import Path

from src.core.config import PROJECT_ROOT
from src.core.logging import logger
from src.core.models import ResponseEnvelope

# One JSON file per fixture key. Created lazily; committed to git so replay mode
# works in CI without an API key.
FIXTURES_DIR = PROJECT_ROOT / "eval" / "fixtures"

_RECORD_COMMAND = (
    'set OPENROUTER_API_KEY, then run LLM_MODE=record '
    '"C:/Users/jun/Desktop/work/OrbitMeshTest/.venv/Scripts/python" eval/runner.py'
)


def fixture_key(messages: list[dict[str, str]]) -> str:
    """Deterministic key: sha256 of the canonical JSON of the messages array."""
    canonical = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_fixture(
    messages: list[dict[str, str]],
    envelope: ResponseEnvelope,
    model_id: str,
    fixtures_dir: Path | None = None,
) -> Path:
    """Persist a live LLM envelope (plus the raw model id that produced it)."""
    target_dir = fixtures_dir or FIXTURES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    key = fixture_key(messages)
    path = target_dir / f"{key}.json"
    payload = {
        "key": key,
        "model": model_id,
        "envelope": envelope.model_dump(mode="json"),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Recorded LLM fixture {key} (model={model_id}) at {path}")
    return path


def load_fixture(
    messages: list[dict[str, str]],
    fixtures_dir: Path | None = None,
) -> ResponseEnvelope:
    """Load the recorded envelope for this prompt, or fail with recording instructions."""
    target_dir = fixtures_dir or FIXTURES_DIR
    key = fixture_key(messages)
    path = target_dir / f"{key}.json"
    if not path.exists():
        raise RuntimeError(
            f"Replay fixture not found for key '{key}' (expected at {path}). "
            f"To record it: {_RECORD_COMMAND}"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ResponseEnvelope.model_validate(payload["envelope"])
