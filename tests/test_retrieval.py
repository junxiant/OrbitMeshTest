"""Retrieval behavior tests: abstention, archived exclusion, meta-point hygiene.

Ingests the real corpus into a scratch Qdrant directory (module-scoped, one
embedding pass) so the shared data/qdrant store is never locked or mutated.
"""
import pytest

from src.ingestion.indexer import VectorIndexer
from src.rag.retriever import HybridRetriever, BM25Index


@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    storage = tmp_path_factory.mktemp("qdrant_retrieval")
    indexer = VectorIndexer(url=None, storage_dir=storage)
    res = indexer.run_ingestion()
    assert res["indexed"] > 0
    return HybridRetriever(indexer=indexer)


def test_out_of_domain_query_abstains(retriever):
    assert retriever.retrieve("What is the capital of France?") == []
    assert retriever.retrieve("chocolate cake recipe") == []
    assert retriever.retrieve("who won the world cup") == []


def test_in_domain_query_returns_chunks(retriever):
    results = retriever.retrieve("My N1 satellite node has a solid amber light")
    assert results
    sources = {c.metadata.source_id for c in results}
    assert sources & {"led-reference", "troubleshooting-guide", "quick-start-guide"}
    for chunk in results:
        assert chunk.text.strip()
        assert chunk.metadata.chunk_id
        assert chunk.metadata.locator


def test_stop_words_alone_cannot_score():
    bm25 = BM25Index()
    assert bm25.search("what is the") == []


def test_archived_band_steering_not_retrievable_by_default(retriever):
    # The "disable band steering" workaround exists only in the archived
    # firmware doc (3.3.x) and must never surface as default evidence.
    results = retriever.retrieve("Should I disable band steering to fix roaming disconnects?")
    for chunk in results:
        assert not chunk.metadata.is_archived
        assert chunk.metadata.source_id != "firmware-archive"
        assert "disable band steering" not in chunk.text.lower()


def test_include_archived_kwarg_surfaces_archive(retriever):
    results = retriever.retrieve(
        "disable band steering workaround roaming instability 3.3.4",
        include_archived=True
    )
    assert any(c.metadata.source_id == "firmware-archive" for c in results)
    assert any(c.metadata.is_archived for c in results)


def test_meta_point_never_surfaces(retriever):
    # Sweep essentially the whole collection: the reserved meta point must not
    # appear as a retrievable chunk in either track or any archived mode.
    results = retriever.retrieve(
        "OrbitMesh router node LED firmware reset network setup",
        top_k=60,
        include_archived=True
    )
    assert results
    for chunk in results:
        assert chunk.metadata.source_id
        assert chunk.metadata.chunk_id
        assert chunk.text.strip()
