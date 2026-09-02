"""Guards for the A6 hygiene changes: test isolation, pinned builds, Makefile safety.

These tests intentionally read repo metadata files (requirements, Makefile,
.env.example, CI workflow) so regressions in the build/test hygiene fail the
suite instead of surfacing later in CI or on a developer machine with a real
API key in .env.
"""
import re
from pathlib import Path

from src.core import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Requirement lines: name[extras]==version (comments and blanks skipped).
_PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,_-]+\])?==[A-Za-z0-9.]+$")


def _requirement_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and not line.startswith("-r "):
            lines.append(line)
    return lines


def test_llm_mode_forced_to_mock() -> None:
    # conftest.py must have won over anything in .env or the caller's shell.
    assert config.LLM_MODE == "mock"
    assert config.OPENROUTER_API_KEY == ""


def test_writable_paths_leave_the_repo() -> None:
    repo = config.PROJECT_ROOT.resolve()
    for path in (
        config.QDRANT_PATH,
        config.SESSIONS_DB_PATH,
        config.LOGS_DIR,
        config.LOG_FILE_PATH,
        config.EVAL_RESULTS_DIR,
    ):
        assert not Path(path).resolve().is_relative_to(repo), (
            f"{path} points inside the repo; tests must only write to temp dirs"
        )


def test_requirements_are_pinned() -> None:
    lines = _requirement_lines(PROJECT_ROOT / "requirements.txt")
    assert len(lines) >= 9
    for line in lines:
        assert _PIN_RE.match(line), f"unpinned requirement: {line!r}"


def test_dev_requirements_are_pinned_and_include_ruff() -> None:
    lines = _requirement_lines(PROJECT_ROOT / "requirements-dev.txt")
    assert any(line.startswith("ruff==") for line in lines)
    for line in lines:
        assert _PIN_RE.match(line), f"unpinned dev requirement: {line!r}"


def test_makefile_targets_and_mock_enforcement() -> None:
    makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ("setup", "ingest", "chat", "test", "eval", "record-fixtures", "eval-live"):
        assert re.search(rf"^{re.escape(target)}:", makefile, re.MULTILINE), (
            f"missing Makefile target: {target}"
        )
    test_body = makefile.split("\ntest:", 1)[1].split("\n\n", 1)[0]
    assert "LLM_MODE=mock" in test_body, "make test must force LLM_MODE=mock"
    record_body = makefile.split("\nrecord-fixtures:", 1)[1].split("\n\n", 1)[0]
    assert "LLM_MODE=record" in record_body
    live_body = makefile.split("\neval-live:", 1)[1].split("\n\n", 1)[0]
    assert "LLM_MODE=live" in live_body


def test_env_example_has_no_committed_key_and_documents_modes() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    match = re.search(r"^OPENROUTER_API_KEY=(.*)$", env_example, re.MULTILINE)
    assert match is not None
    assert match.group(1).strip() == "", ".env.example must never carry a key value"
    for mode in ("mock", "live", "replay", "record"):
        assert mode in env_example, f"LLM_MODE value '{mode}' undocumented in .env.example"


def test_ci_workflow_caches_models_and_lints() -> None:
    ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "actions/cache" in ci, "CI must cache the embedding model downloads"
    assert "ruff check" in ci, "CI must run the ruff lint gate"
    assert "LLM_MODE: mock" in ci
    assert "QDRANT_PATH" in ci
