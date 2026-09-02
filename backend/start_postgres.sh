#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "Starting PostgreSQL database container..."
docker compose up -d postgres adminer

echo "PostgreSQL is starting on localhost:5432 (Database: orbitmesh, User: orbitmesh)"
