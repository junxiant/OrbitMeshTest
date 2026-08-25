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
"$PYTHON_CMD" -m src.ingestion.indexer
