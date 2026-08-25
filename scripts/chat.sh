#!/usr/bin/env bash
set -e

if command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "Python interpreter not found in PATH" >&2
    exit 1
fi

export PYTHONPATH=".:$PYTHONPATH"

if [ "$1" == "--jsonl" ]; then
    "$PYTHON_CMD" -m src.cli.jsonl_runner
else
    "$PYTHON_CMD" -m src.cli.interactive
fi
