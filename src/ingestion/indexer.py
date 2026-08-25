from __future__ import annotations
import uuid
import warnings
from pathlib import Path
from typing import Iterator, List, Optional, Set, Dict

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from src.core.config import (
    CORPUS_DIR,
    MANIFEST_PATH,
    QDRANT_URL,
    QDRANT_STORAGE_DIR,
    EMBEDDING_DIMENSION,
    ensure_dirs,
)
from src.core.models import DocumentChunk
from src.core.logging import logger
from src.ingestion.parser import MarkdownCorpusParser
from src.rag.embeddings import LocalEmbedder, EMBEDDER_FINGERPRINT

# Reserved point that stores collection-level metadata (embedder fingerprint,
# manifest version). It carries a zero vector and payload {"is_meta": true, ...}
# and must be excluded from every search, scroll, and count.
META_POINT_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "collection-meta"))


def not_meta_condition() -> qmodels.FieldCondition:
    """Filter condition matching meta points; use inside `must_not`."""
    return qmodels.FieldCondition(key="is_meta", match=qmodels.MatchValue(value=True))


# Indexing into Vector DB
class VectorIndexer:
    COLLECTION_NAME = "orbitmesh_knowledge"
    VECTOR_DIMENSION = EMBEDDING_DIMENSION
    _SCROLL_PAGE_SIZE = 256

    def __init__(
        self,
        url: Optional[str] = QDRANT_URL,
        storage_dir: Optional[Path] = None,
        db_dir: Optional[Path] = None
    ):
        target_dir = storage_dir or db_dir or QDRANT_STORAGE_DIR
        self.embedder = LocalEmbedder()
        self.is_remote = False
        self.client = self._init_client(url, target_dir)
        self._init_collection()

    _client_cache: Dict[str, QdrantClient] = {}

    def _init_client(self, url: Optional[str], storage_dir: Path) -> QdrantClient:
        storage_dir = Path(storage_dir)
        cache_key = url if url else str(storage_dir.resolve())
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]

        if url:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    client = QdrantClient(url=url, timeout=3.0, check_compatibility=False)
                    client.get_collections()
                self.is_remote = True
                logger.info(f"Connected to remote Qdrant server at {url}")
                self._client_cache[cache_key] = client
                return client
            except Exception:
                logger.warning(f"Qdrant server not running at {url}. Using local embedded storage.")

        storage_dir.mkdir(parents=True, exist_ok=True)
        self.is_remote = False
        logger.info(f"Using local embedded Qdrant storage at {storage_dir}")
        client = QdrantClient(path=str(storage_dir))
        self._client_cache[cache_key] = client
        return client

    def _init_collection(self) -> None:
        try:
            if not self.client.collection_exists(self.COLLECTION_NAME):
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=qmodels.VectorParams(
                        size=self.VECTOR_DIMENSION,
                        distance=qmodels.Distance.COSINE
                    )
                )
                if self.is_remote:
                    self.client.create_payload_index(
                        collection_name=self.COLLECTION_NAME,
                        field_name="product_line",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD
                    )
                    self.client.create_payload_index(
                        collection_name=self.COLLECTION_NAME,
                        field_name="is_archived",
                        field_schema=qmodels.PayloadSchemaType.BOOL
                    )
                    self.client.create_payload_index(
                        collection_name=self.COLLECTION_NAME,
                        field_name="source_id",
                        field_schema=qmodels.PayloadSchemaType.KEYWORD
                    )
                    self.client.create_payload_index(
                        collection_name=self.COLLECTION_NAME,
                        field_name="is_meta",
                        field_schema=qmodels.PayloadSchemaType.BOOL
                    )
                logger.info(f"Created Qdrant collection: {self.COLLECTION_NAME}")
        except Exception as e:
            logger.error(f"Error initializing Qdrant collection: {e}")

    def count(self) -> int:
        """Number of content points in the collection (meta point excluded)."""
        try:
            res = self.client.count(
                collection_name=self.COLLECTION_NAME,
                count_filter=qmodels.Filter(must_not=[not_meta_condition()]),
                exact=True
            )
            return res.count
        except Exception:
            return 0

    # -- Collection meta point -------------------------------------------------

    def read_meta(self) -> Optional[dict]:
        """Payload of the reserved meta point, or None if absent."""
        try:
            points = self.client.retrieve(
                collection_name=self.COLLECTION_NAME,
                ids=[META_POINT_ID],
                with_payload=True,
                with_vectors=False
            )
        except Exception as e:
            logger.warning(f"Error reading collection meta point: {e}")
            return None
        if not points:
            return None
        return points[0].payload or {}

    def check_embedder_compatibility(self) -> None:
        """Raise if the stored vectors were produced by a different embedder."""
        meta = self.read_meta()
        if meta is None:
            if self.count() > 0:
                logger.warning(
                    "Collection has points but no embedder fingerprint (index predates "
                    f"fingerprinting). Assuming current embedder '{EMBEDDER_FINGERPRINT}'."
                )
            return
        stored = meta.get("embedder", "")
        if stored and stored != EMBEDDER_FINGERPRINT:
            raise RuntimeError(
                f"Embedder mismatch: collection '{self.COLLECTION_NAME}' was built with "
                f"'{stored}' but the current embedder is '{EMBEDDER_FINGERPRINT}'. "
                "Delete the Qdrant storage (or collection) and re-run ingestion."
            )

    def _write_meta(self, manifest_version: Optional[str]) -> None:
        payload = {
            "is_meta": True,
            "embedder": EMBEDDER_FINGERPRINT,
            "manifest_version": manifest_version or "",
        }
        self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[qmodels.PointStruct(
                id=META_POINT_ID,
                vector=[0.0] * self.VECTOR_DIMENSION,
                payload=payload
            )],
            wait=True
        )

    # -- Scroll helpers --------------------------------------------------------

    def _scroll_filtered(
        self,
        scroll_filter: qmodels.Filter,
        with_payload: bool | list[str] = True
    ) -> Iterator[qmodels.Record]:
        """Paginated scroll over points matching a filter (never loads everything at once)."""
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=scroll_filter,
                limit=self._SCROLL_PAGE_SIZE,
                offset=offset,
                with_payload=with_payload,
                with_vectors=False
            )
            yield from points
            if offset is None:
                break

    def _scroll_source(self, source_id: str) -> Iterator[qmodels.Record]:
        """All content points belonging to one source document."""
        return self._scroll_filtered(
            qmodels.Filter(
                must=[qmodels.FieldCondition(key="source_id", match=qmodels.MatchValue(value=source_id))],
                must_not=[not_meta_condition()]
            )
        )

    def _stored_source_ids(self) -> Set[str]:
        """Distinct source_ids currently stored (payload-light paginated scroll)."""
        sources: Set[str] = set()
        records = self._scroll_filtered(
            qmodels.Filter(must_not=[not_meta_condition()]),
            with_payload=["source_id"]
        )
        for pt in records:
            payload = pt.payload or {}
            src = payload.get("source_id")
            if src:
                sources.add(src)
        return sources

    # -- Ingestion -------------------------------------------------------------

    def index_chunks(
        self,
        chunks: List[DocumentChunk],
        manifest_source_ids: Optional[Set[str]] = None,
        manifest_version: Optional[str] = None
    ) -> dict:
        """Upsert chunks and reconcile the collection.

        - Modified docs: chunks of an incoming source that no longer exist are deleted.
        - Deleted/renamed docs: when `manifest_source_ids` is provided, every stored
          source absent from BOTH the manifest and the incoming batch loses all its
          points. When it is None (direct/partial calls) orphan reconciliation is
          skipped, preserving legacy call-site behavior.
        """
        if not chunks:
            logger.warning("No chunks provided for indexing.")
            return {"total": 0, "indexed": 0, "duplicates_skipped": 0, "stale_deleted": 0, "orphans_deleted": 0}

        self.check_embedder_compatibility()

        # 1. Map incoming chunks by source_id
        incoming_by_source: Dict[str, Set[str]] = {}
        for c in chunks:
            incoming_by_source.setdefault(c.metadata.source_id, set()).add(c.metadata.chunk_id)

        # 2. Per-source filtered scrolls: find stale chunks of modified docs and
        #    already-indexed chunk ids (no full-collection dump).
        stale_point_ids = []
        existing_ids: Set[str] = set()
        try:
            for source_id, incoming_chunk_ids in incoming_by_source.items():
                for pt in self._scroll_source(source_id):
                    payload = pt.payload or {}
                    pt_chunk_id = payload.get("chunk_id")
                    if pt_chunk_id not in incoming_chunk_ids:
                        stale_point_ids.append(pt.id)
                    else:
                        existing_ids.add(pt_chunk_id)
                        existing_ids.add(str(pt.id))
        except Exception as e:
            logger.warning(f"Error reading existing points for reconciliation: {e}")

        # 3. Purge stale points of modified documents
        if stale_point_ids:
            try:
                self.client.delete(
                    collection_name=self.COLLECTION_NAME,
                    points_selector=qmodels.PointIdsList(points=stale_point_ids),
                    wait=True
                )
                logger.info(f"Reconciled source documents: deleted {len(stale_point_ids)} stale chunk(s).")
            except Exception as e:
                logger.error(f"Error deleting stale points: {e}")

        # 4. Filter for new chunks to index
        new_chunks = [c for c in chunks if c.metadata.chunk_id not in existing_ids]
        skipped_count = len(chunks) - len(new_chunks)

        if new_chunks:
            # Prepend document title and hierarchical breadcrumb header path to contextualize dense embedding
            texts = []
            for c in new_chunks:
                breadcrumb = " > ".join(c.metadata.header_path) if c.metadata.header_path else c.metadata.locator
                header_prefix = f"[{c.metadata.doc_title}] {breadcrumb}"
                texts.append(f"{header_prefix}\n\n{c.text}")

            embeddings = self.embedder.embed_documents(texts)

            points = []
            for i, c in enumerate(new_chunks):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, c.metadata.chunk_id))
                payload = {
                    "chunk_id": c.metadata.chunk_id,
                    "text": c.text,
                    "source_id": c.metadata.source_id,
                    "doc_title": c.metadata.doc_title,
                    "locator": c.metadata.locator,
                    "header_path": c.metadata.header_path,
                    "product_line": c.metadata.product_line or "All",
                    "is_archived": c.metadata.is_archived,
                    "version": c.metadata.version or "",
                    "effective_date": c.metadata.effective_date or "",
                    "sha256": c.metadata.sha256,
                }
                points.append(qmodels.PointStruct(id=point_id, vector=embeddings[i], payload=payload))

            self.client.upsert(
                collection_name=self.COLLECTION_NAME,
                points=points,
                wait=True
            )
        else:
            logger.info(f"All {len(chunks)} chunks are already indexed (Idempotent).")

        # 5. Manifest-driven reconciliation: drop sources that were deleted/renamed.
        orphans_deleted = self._reconcile_orphan_sources(
            manifest_source_ids, set(incoming_by_source)
        ) if manifest_source_ids is not None else 0

        # 6. Refresh the collection meta point (embedder fingerprint + manifest version).
        self._write_meta(manifest_version)

        logger.info(
            f"Ingestion reconciled: indexed {len(new_chunks)} new chunk(s), skipped {skipped_count} "
            f"duplicate(s), deleted {len(stale_point_ids)} stale chunk(s), "
            f"deleted {orphans_deleted} orphaned chunk(s) from removed documents."
        )
        return {
            "total": len(chunks),
            "indexed": len(new_chunks),
            "duplicates_skipped": skipped_count,
            "stale_deleted": len(stale_point_ids),
            "orphans_deleted": orphans_deleted
        }

    def _reconcile_orphan_sources(self, manifest_source_ids: Set[str], incoming_sources: Set[str]) -> int:
        """Delete every point whose source is in neither the manifest nor the incoming batch."""
        try:
            stored_sources = self._stored_source_ids()
        except Exception as e:
            logger.warning(f"Error enumerating stored sources for reconciliation: {e}")
            return 0

        orphan_sources = stored_sources - manifest_source_ids - incoming_sources
        if not orphan_sources:
            return 0

        orphan_filter = qmodels.Filter(
            must=[qmodels.FieldCondition(
                key="source_id",
                match=qmodels.MatchAny(any=sorted(orphan_sources))
            )],
            must_not=[not_meta_condition()]
        )
        try:
            orphan_count = self.client.count(
                collection_name=self.COLLECTION_NAME,
                count_filter=orphan_filter,
                exact=True
            ).count
            self.client.delete(
                collection_name=self.COLLECTION_NAME,
                points_selector=qmodels.FilterSelector(filter=orphan_filter),
                wait=True
            )
            logger.info(
                f"Deleted {orphan_count} chunk(s) from {len(orphan_sources)} removed document(s): "
                f"{', '.join(sorted(orphan_sources))}"
            )
            return orphan_count
        except Exception as e:
            logger.error(f"Error deleting orphaned sources {sorted(orphan_sources)}: {e}")
            return 0

    def run_ingestion(self, corpus_dir: Path = CORPUS_DIR, manifest_path: Optional[Path] = MANIFEST_PATH) -> dict:
        parser = MarkdownCorpusParser(corpus_dir, manifest_path)
        chunks = parser.parse_all()
        result = self.index_chunks(
            chunks,
            manifest_source_ids=parser.manifest_source_ids if parser.manifest_loaded else None,
            manifest_version=parser.manifest_version
        )
        return result


def main():
    ensure_dirs()
    indexer = VectorIndexer()
    res = indexer.run_ingestion()
    print(
        f"Ingestion completed: Total={res['total']}, Indexed={res['indexed']}, "
        f"Duplicates Skipped={res['duplicates_skipped']}, Stale Deleted={res['stale_deleted']}, "
        f"Orphans Deleted={res['orphans_deleted']}"
    )


if __name__ == "__main__":
    main()
