ARG QDRANT_VERSION=v1.14.1
FROM qdrant/qdrant:${QDRANT_VERSION}

LABEL org.opencontainers.image.title="OrbitMesh take-home Qdrant"
LABEL org.opencontainers.image.description="Optional local vector database for the assignment"

EXPOSE 6333 6334

# The upstream image includes Bash. This checks that Qdrant's HTTP port accepts
# connections without installing extra packages in the image.
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=12 \
  CMD ["bash", "-c", ":> /dev/tcp/127.0.0.1/6333"]

