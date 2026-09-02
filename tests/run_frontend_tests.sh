#!/usr/bin/env bash
set -e
set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

cd "$FRONTEND_DIR"

# Setup logs directory and timestamped log file
mkdir -p "$PROJECT_ROOT/logs"
LOG_FILE="$PROJECT_ROOT/logs/frontend_test_$(date +%Y%m%d_%H%M%S).log"

echo "=== Running OrbitMesh React Frontend Test Suite ==="

npm test -- "$@" | tee "$LOG_FILE"

echo "Frontend tests completed."
echo "Test output saved to: $LOG_FILE"
