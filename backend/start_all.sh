#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== Starting Full OrbitMesh Backend Services ==="

# 1. Start Qdrant and PostgreSQL containers
echo "Starting PostgreSQL and Qdrant containers..."
docker compose up -d --build

# 2. Wait for PostgreSQL and Qdrant to be ready
echo "Waiting for services to be ready..."
max_retries=15
count=0

until nc -z localhost 5432 2>/dev/null || (echo > /dev/tcp/127.0.0.1/5432) 2>/dev/null || [ $count -ge $max_retries ]; do
    echo "Waiting for PostgreSQL (localhost:5432)..."
    sleep 1
    count=$((count + 1))
done

count=0
until nc -z localhost 6333 2>/dev/null || (echo > /dev/tcp/127.0.0.1/6333) 2>/dev/null || [ $count -ge $max_retries ]; do
    echo "Waiting for Qdrant (localhost:6333)..."
    sleep 1
    count=$((count + 1))
done

echo "PostgreSQL and Qdrant are ready."

# 3. Ingest corpus into Qdrant if collection is empty or uninitialized
POINTS=$(curl -s http://localhost:6333/collections/orbitmesh_knowledge | grep -o '"points_count":[0-9]*' | cut -d: -f2 || echo 0)
if [ -z "$POINTS" ] || [ "$POINTS" -le 1 ]; then
    echo "Qdrant collection empty or uninitialized. Ingesting knowledge corpus..."
    "$PROJECT_ROOT/scripts/ingest.sh"
else
    echo "Corpus already ingested ($POINTS points found in Qdrant). Skipping ingestion."
fi

# 4. Start FastAPI Server
echo "Starting FastAPI server..."
exec "$SCRIPT_DIR/start_api.sh"
