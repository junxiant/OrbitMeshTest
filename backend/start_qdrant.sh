#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "Starting Qdrant vector database container..."
docker compose up -d --build qdrant

echo "Qdrant server is running on http://localhost:6333 (gRPC: 6334)"
