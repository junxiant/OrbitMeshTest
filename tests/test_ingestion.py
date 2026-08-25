import json

import pytest
from pathlib import Path
from src.ingestion.parser import MarkdownCorpusParser
from src.ingestion.indexer import VectorIndexer, META_POINT_ID
from src.rag.embeddings import EMBEDDER_FINGERPRINT
from src.rag.retriever import HybridRetriever
from src.core.config import CORPUS_DIR, MANIFEST_PATH


def write_scratch_corpus(corpus_dir: Path, docs: dict[str, str], manifest_version: str = "test-1") -> Path:
    """Write markdown docs plus a manifest that lists exactly those docs."""
    corpus_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"corpus": "test", "version": manifest_version, "documents": []}
    for doc_id, text in docs.items():
        (corpus_dir / f"{doc_id}.md").write_text(text, encoding="utf-8")
        manifest["documents"].append({
            "id": doc_id,
            "title": doc_id.replace("-", " ").title(),
            "path": f"{doc_id}.md",
            "format": "markdown",
            "version": "1.0",
            "effective_date": "2026-01-01",
            "product_line": "Standard",
        })
    manifest_path = corpus_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


ALPHA_DOC = "# Alpha Guide\n\n## Pairing\nHold the pair button for 3 seconds.\n\n## Lights\nThe LED pulses blue while pairing.\n"
BETA_DOC = "# Beta Guide\n\n## Recovery\nHold reset for 15 seconds to recover the unit.\n"


def test_parser_loads_manifest_and_chunks():
    parser = MarkdownCorpusParser(CORPUS_DIR, MANIFEST_PATH)
    chunks = parser.parse_all()
    assert len(chunks) > 0
    for chunk in chunks:
        assert chunk.metadata.source_id != ""
        assert chunk.metadata.locator != ""
        assert chunk.metadata.sha256 != ""
        assert chunk.text.strip() != ""


def test_idempotent_indexing(tmp_path):
    parser = MarkdownCorpusParser(CORPUS_DIR, MANIFEST_PATH)
    chunks = parser.parse_all()
    indexer = VectorIndexer(url=None, storage_dir=tmp_path / "qdrant_idempotent")

    # First run
    res1 = indexer.index_chunks(chunks)
    assert res1["indexed"] == len(chunks)
    assert res1["duplicates_skipped"] == 0

    # Second run
    res2 = indexer.index_chunks(chunks)
    assert res2["indexed"] == 0
    assert res2["duplicates_skipped"] == len(chunks)


def test_updated_document_reconciliation(tmp_path):
    temp_corpus = tmp_path / "corpus"
    temp_corpus.mkdir()
    doc_path = temp_corpus / "sample-guide.md"
    doc_path.write_text(
        "# Sample Guide\n\n## Section One\nHold reset for 15 seconds to recover.\n\n## Section Two\nLED is solid white.\n",
        encoding="utf-8"
    )

    parser = MarkdownCorpusParser(temp_corpus)
    initial_chunks = parser.parse_all()
    assert len(initial_chunks) == 3

    indexer = VectorIndexer(url=None, storage_dir=tmp_path / "qdrant_update_test")
    res1 = indexer.index_chunks(initial_chunks)
    assert res1["indexed"] == 3
    assert res1["stale_deleted"] == 0
    assert indexer.count() == 3

    # Mutate document
    doc_path.write_text(
        "# Sample Guide\n\n## Section One\nHold reset for 20 seconds to recover.\n\n## Section Two\nLED is solid white.\n",
        encoding="utf-8"
    )

    updated_chunks = parser.parse_all()
    assert len(updated_chunks) == 3

    res2 = indexer.index_chunks(updated_chunks)
    assert res2["indexed"] == 1
    assert res2["duplicates_skipped"] == 2
    assert res2["stale_deleted"] == 1
    assert indexer.count() == 3


def test_deleted_document_reconciliation(tmp_path):
    corpus = tmp_path / "corpus"
    manifest_path = write_scratch_corpus(corpus, {"alpha-guide": ALPHA_DOC, "beta-guide": BETA_DOC})

    indexer = VectorIndexer(url=None, storage_dir=tmp_path / "qdrant_delete_test")
    res1 = indexer.run_ingestion(corpus_dir=corpus, manifest_path=manifest_path)
    assert res1["indexed"] > 0
    assert indexer._stored_source_ids() == {"alpha-guide", "beta-guide"}
    beta_chunks = res1["total"] - len(MarkdownCorpusParser(corpus, manifest_path).parse_file(corpus / "alpha-guide.md"))

    # Remove beta-guide from disk AND from the manifest, then re-ingest.
    (corpus / "beta-guide.md").unlink()
    write_scratch_corpus(corpus, {"alpha-guide": ALPHA_DOC})

    res2 = indexer.run_ingestion(corpus_dir=corpus, manifest_path=manifest_path)
    assert res2["orphans_deleted"] == beta_chunks
    assert indexer._stored_source_ids() == {"alpha-guide"}
    assert indexer.count() == res2["total"]


def test_renamed_document_reconciliation(tmp_path):
    corpus = tmp_path / "corpus"
    manifest_path = write_scratch_corpus(corpus, {"alpha-guide": ALPHA_DOC, "beta-guide": BETA_DOC})

    indexer = VectorIndexer(url=None, storage_dir=tmp_path / "qdrant_rename_test")
    indexer.run_ingestion(corpus_dir=corpus, manifest_path=manifest_path)
    assert indexer._stored_source_ids() == {"alpha-guide", "beta-guide"}

    # Rename beta-guide -> gamma-guide (same content, new id) in disk + manifest.
    (corpus / "beta-guide.md").unlink()
    write_scratch_corpus(corpus, {"alpha-guide": ALPHA_DOC, "gamma-guide": BETA_DOC})

    res2 = indexer.run_ingestion(corpus_dir=corpus, manifest_path=manifest_path)
    assert res2["orphans_deleted"] > 0
    assert indexer._stored_source_ids() == {"alpha-guide", "gamma-guide"}


def test_meta_point_written_and_excluded_from_count(tmp_path):
    corpus = tmp_path / "corpus"
    manifest_path = write_scratch_corpus(corpus, {"alpha-guide": ALPHA_DOC}, manifest_version="v-42")

    indexer = VectorIndexer(url=None, storage_dir=tmp_path / "qdrant_meta_test")
    res = indexer.run_ingestion(corpus_dir=corpus, manifest_path=manifest_path)

    meta = indexer.read_meta()
    assert meta is not None
    assert meta["is_meta"] is True
    assert meta["embedder"] == EMBEDDER_FINGERPRINT
    assert meta["manifest_version"] == "v-42"
    # count() must exclude the meta point: only content chunks are counted.
    assert indexer.count() == res["total"]


def test_mismatched_embedder_fingerprint_raises(tmp_path):
    corpus = tmp_path / "corpus"
    manifest_path = write_scratch_corpus(corpus, {"alpha-guide": ALPHA_DOC})

    indexer = VectorIndexer(url=None, storage_dir=tmp_path / "qdrant_fingerprint_test")
    indexer.run_ingestion(corpus_dir=corpus, manifest_path=manifest_path)

    # Simulate an index built by a different embedder.
    indexer.client.set_payload(
        collection_name=indexer.COLLECTION_NAME,
        payload={"embedder": "other-model:999"},
        points=[META_POINT_ID],
        wait=True
    )

    with pytest.raises(RuntimeError, match="Embedder mismatch"):
        indexer.check_embedder_compatibility()

    # The retriever must refuse to start against an incompatible index.
    with pytest.raises(RuntimeError, match="Embedder mismatch"):
        HybridRetriever(indexer=indexer, corpus_dir=corpus, manifest_path=manifest_path)
