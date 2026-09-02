#!/usr/bin/env bash
set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Activate virtual environment if available
if [ -d "$PROJECT_ROOT/venv" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
elif [ -d "$PROJECT_ROOT/.venv" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
fi

# Set test environment to deterministic offline mock mode
export LLM_MODE=mock
export PYTHONPATH=.
export REQUIRE_API_KEY=false

# Setup logs directory and timestamped log file
mkdir -p "$PROJECT_ROOT/logs"
LOG_FILE="$PROJECT_ROOT/logs/backend_test_$(date +%Y%m%d_%H%M%S).log"

echo "=== Running OrbitMesh FastAPI Backend Test Suite ==="

# Check if pytest-cov is installed
COV_ARGS=()
if python -c "import pytest_cov" >/dev/null 2>&1; then
    COV_ARGS=("--cov=backend" "--cov-report=term-missing")
else
    echo "Note: pytest-cov is not installed in the environment. Running tests without coverage report."
    echo "To enable coverage: pip install pytest-cov"
fi

pytest tests/test_backend_api.py -v "${COV_ARGS[@]}" "$@" | tee "$LOG_FILE"

echo "Backend tests completed."
echo "Test output saved to: $LOG_FILE"
