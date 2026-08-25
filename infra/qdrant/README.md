# Optional Qdrant service

Start the local vector database:

```bash
docker compose up -d --build --wait
```

The HTTP API is available at `http://localhost:6333` and the dashboard at
`http://localhost:6333/dashboard`. Data persists in the `qdrant_data` Docker
volume.

Check status or stop it with:

```bash
docker compose ps
docker compose down
```

Use `docker compose down -v` only when you intend to delete the indexed data.
Qdrant is optional; candidates may use another vector database.

