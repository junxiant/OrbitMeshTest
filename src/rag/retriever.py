from __future__ import annotations
import math
import re
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from collections import Counter

from qdrant_client.http import models as qmodels

from src.core.models import DocumentChunk, ChunkMetadata
from src.core.config import CORPUS_DIR, MANIFEST_PATH, DENSE_SCORE_FLOOR, BM25_SCORE_FLOOR
from src.core.logging import logger
from src.ingestion.indexer import VectorIndexer, not_meta_condition
from src.ingestion.parser import MarkdownCorpusParser

# English stop words excluded from BM25 scoring so that function-word-only
# queries ("what is the ...") cannot accumulate lexical score against the
# corpus. Kept deliberately small: product terms (n1, r1, red, reset, ...)
# are never stop words.
BM25_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "if", "then", "than",
    "this", "that", "these", "those", "there", "here",
    "i", "you", "he", "she", "we", "they", "it", "me", "us", "them",
    "my", "your", "his", "her", "its", "our", "their",
    "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "doing", "have", "has", "had", "having",
    "will", "would", "can", "could", "should", "shall", "may", "might", "must",
    "of", "to", "in", "on", "for", "with", "at", "by", "from", "as", "about", "into",
    "what", "which", "who", "whom", "when", "where", "why", "how",
    "all", "any", "both", "each", "some", "such", "so", "too", "very",
    "just", "now", "please",
    # Contraction fragments produced by \w+ tokenization ("what's" -> "what", "s";
    # "don't" -> "don", "t"). Without these, possessive "s" in the corpus gives
    # arbitrary queries a lexical score.
    "s", "t", "m", "d", "ll", "re", "ve",
    "don", "didn", "doesn", "isn", "aren", "wasn", "weren", "won",
    "wouldn", "couldn", "shouldn", "hasn", "haven", "hadn", "ain",
})


# Keyword Ranking
class BM25Index:
    """In-memory Okapi BM25 Index for lexical search over corpus chunks."""
    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        corpus_dir: Optional[Path] = None,
        manifest_path: Optional[Path] = None
    ):
        self.k1 = k1
        self.b = b
        self.corpus_dir = Path(corpus_dir) if corpus_dir else CORPUS_DIR
        self.manifest_path = Path(manifest_path) if manifest_path else MANIFEST_PATH
        self.chunks: List[DocumentChunk] = []
        self.doc_len: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_term_freqs: List[Counter] = []
        self._build_index()

    def _tokenize(self, text: str) -> List[str]:
        return [t for t in re.findall(r"\w+", text.lower()) if t not in BM25_STOP_WORDS]

    def _build_index(self) -> None:
        try:
            parser = MarkdownCorpusParser(self.corpus_dir, self.manifest_path)
            self.chunks = parser.parse_all()
        except Exception as e:
            logger.warning(f"Failed to load corpus chunks for BM25: {e}")
            self.chunks = []

        if not self.chunks:
            return

        total_tokens = 0
        self.doc_len = []
        self.doc_term_freqs = []
        self.doc_freqs = {}

        for c in self.chunks:
            tokens = self._tokenize(c.text + " " + c.metadata.locator + " " + c.metadata.doc_title)
            self.doc_len.append(len(tokens))
            total_tokens += len(tokens)
            tf = Counter(tokens)
            self.doc_term_freqs.append(tf)

            for term in tf:
                self.doc_freqs[term] = self.doc_freqs.get(term, 0) + 1

        n_docs = len(self.chunks)
        self.avg_doc_len = total_tokens / max(n_docs, 1)

        for term, df in self.doc_freqs.items():
            self.idf[term] = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        top_k: int = 10,
        product_line: Optional[str] = None,
        include_archived: bool = False
    ) -> List[Tuple[float, DocumentChunk]]:
        query_tokens = self._tokenize(query)
        if not query_tokens or not self.chunks:
            return []

        scores: List[Tuple[float, DocumentChunk]] = []

        for idx, chunk in enumerate(self.chunks):
            # Apply metadata filters
            meta = chunk.metadata
            if not include_archived and meta.is_archived:
                continue
            if product_line and product_line in ["Standard", "Pro"]:
                if meta.product_line and meta.product_line not in [product_line, "All"]:
                    continue

            score = 0.0
            doc_len = self.doc_len[idx]
            tf_dict = self.doc_term_freqs[idx]

            for term in query_tokens:
                if term not in tf_dict:
                    continue
                idf_val = self.idf.get(term, 0.0)
                tf_val = tf_dict[term]
                num = tf_val * (self.k1 + 1.0)
                denom = tf_val + self.k1 * (1.0 - self.b + self.b * (doc_len / max(self.avg_doc_len, 1e-5)))
                score += idf_val * (num / denom)

            if score > 0.0:
                scores.append((score, chunk))

        scores.sort(key=lambda x: x[0], reverse=True)
        return scores[:top_k]


# Dual-Track Hybrid Retriever: Dense Qdrant + Lexical BM25 with Reciprocal Rank Fusion (RRF)
class HybridRetriever:
    def __init__(
        self,
        indexer: Optional[VectorIndexer] = None,
        corpus_dir: Optional[Path] = None,
        manifest_path: Optional[Path] = None
    ):
        self.indexer = indexer or VectorIndexer()
        self.client = self.indexer.client
        self.embedder = self.indexer.embedder
        self.collection_name = self.indexer.COLLECTION_NAME
        # Fail loudly if the stored vectors were produced by a different embedder
        # than the one that will embed queries (RuntimeError on mismatch).
        self.indexer.check_embedder_compatibility()
        self.bm25_index = BM25Index(corpus_dir=corpus_dir, manifest_path=manifest_path)

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        product_line: Optional[str] = None,
        include_archived: bool = False,
        score_threshold: float = 0.015
    ) -> List[DocumentChunk]:
        """Hybrid retrieval with abstention: returns [] for out-of-domain queries.

        RRF ranks cannot signal relevance (rank 1 exists for any query), so the
        abstention gate runs on RAW per-track scores BEFORE fusion: if the best
        dense cosine similarity is below DENSE_SCORE_FLOOR AND the best BM25
        score is below BM25_SCORE_FLOOR, the retriever abstains.

        Floors tuned empirically on 2026-08-25 against the full 56-chunk corpus
        (bge-small-en-v1.5, archived/meta excluded, stop-worded BM25) via a
        scratch probe re-ingesting the corpus into a throwaway Qdrant dir.
        Measured best dense cosine / best BM25 per query:
          In-domain (10 inputs from eval/cases.jsonl), all must pass:
            "My N1 satellite node has a solid amber light"       0.774 / 9.68
            "The N1 node is flashing red continuously"           0.745 / 7.93
            "My R1 main router ... solid red light no internet"  0.733 / 13.33
            "How do I set up my new OrbitMesh R5 Pro gateway?"   0.874 / 11.31
            "What is the latest stable firmware version ..."     0.869 / 4.75
            "My wireless N1 node keeps disconnecting ..."        0.766 / 7.15
            "My N1 is connected via Ethernet ... drops out"      0.765 / 10.74
            "wifey box nod1 blnk yellow no worky internet ..."   0.687 / 4.45
            "How do I configure the 10Gbps SFP+ ... on my N1"    0.723 / 4.68
            "I want to factory reset everything to start fresh"  0.690 / 7.38
          Out-of-domain (8), all must abstain:
            "What is the capital of France?"                     0.406 / 0.00
            "chocolate cake recipe"                              0.469 / 0.00
            "python list comprehension"                          0.450 / 0.00
            "who won the world cup"                              0.477 / 0.00
            "how do I tie a tie"                                 0.573 / 0.00
            "best stocks to buy right now"                       0.539 / 0.00
            "translate hello to spanish"                         0.509 / 0.00
            "what's the weather like tomorrow"                   0.549 / 0.00
        Margins: DENSE_SCORE_FLOOR 0.62 sits between the out-of-domain max
        (0.573) and the in-domain min (0.687); BM25_SCORE_FLOOR 2.5 sits
        between 0.00 and the in-domain min (4.45). A query is answered if
        EITHER track clears its floor; both floors are env-overridable
        (DENSE_SCORE_FLOOR / BM25_SCORE_FLOOR).

        Take notes:
        If corpus increases need to modify these values / recalculate.
        Different Embedding models will also require a change in the dense score.

        Scale 100x, move BM25Index and RRF to Qdrant server.
        HybridRankFusion in qdrant-sdk can do this natively.

        Also, run automated calibration.

        """
        total_count = self.indexer.count()
        if total_count == 0:
            logger.warning("Vector collection is empty. Run ingestion first.")
            return []

        # 1. Track A: Lexical BM25 Search
        bm25_candidates = self.bm25_index.search(
            query=query,
            top_k=top_k * 3,
            product_line=product_line,
            include_archived=include_archived
        )

        # 2. Track B: Dense Vector Search in Qdrant
        query_embedding = self.embedder.embed_query(query)
        must_conditions = []
        if not include_archived:
            must_conditions.append(
                qmodels.FieldCondition(
                    key="is_archived",
                    match=qmodels.MatchValue(value=False)
                )
            )

        if product_line and product_line in ["Standard", "Pro"]:
            must_conditions.append(
                qmodels.FieldCondition(
                    key="product_line",
                    match=qmodels.MatchAny(any=[product_line, "All"])
                )
            )

        # The reserved collection-meta point must never surface as evidence.
        query_filter = qmodels.Filter(
            must=must_conditions or None,
            must_not=[not_meta_condition()]
        )
        # 3 x top_k documents
        limit = min(top_k * 3, max(total_count, 1))

        dense_points = []
        try:
            if hasattr(self.client, "query_points"):
                response = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                )
                dense_points = response.points
            else:
                dense_points = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                    with_payload=True
                )
        except Exception as e:
            logger.error(f"Error querying dense index in Qdrant: {e}")

        # 3. Abstention gate on raw per-track scores (before fusion, see docstring)
        best_dense = max((hit.score for hit in dense_points), default=0.0)
        best_bm25 = bm25_candidates[0][0] if bm25_candidates else 0.0
        # The gating. RRF gets rank position, not quality of match. 
        # RRF always returns a rank 1, might skew scores.
        # Prevent hallucination
        if best_dense < DENSE_SCORE_FLOOR and best_bm25 < BM25_SCORE_FLOOR:
            logger.info(
                f"Retriever abstained: best dense {best_dense:.3f} < {DENSE_SCORE_FLOOR} and "
                f"best BM25 {best_bm25:.3f} < {BM25_SCORE_FLOOR} for query '{query[:50]}'"
            )
            return []

        # 4. Reciprocal Rank Fusion (RRF)
        rrf_k = 60.0
        rrf_scores: Dict[str, float] = {}
        chunk_map: Dict[str, DocumentChunk] = {}

        # Dense ranks
        for rank, hit in enumerate(dense_points, start=1):
            payload = hit.payload or {}
            chunk_id = payload.get("chunk_id", str(hit.id))
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (rrf_k + rank))
            if chunk_id not in chunk_map:
                chunk_meta = ChunkMetadata(
                    chunk_id=chunk_id,
                    source_id=payload.get("source_id", ""),
                    doc_title=payload.get("doc_title", ""),
                    locator=payload.get("locator", ""),
                    product_line=payload.get("product_line"),
                    is_archived=bool(payload.get("is_archived", False)),
                    effective_date=payload.get("effective_date"),
                    version=payload.get("version"),
                    header_path=payload.get("header_path", []),
                    sha256=payload.get("sha256", ""),
                )
                chunk_map[chunk_id] = DocumentChunk(text=payload.get("text", ""), metadata=chunk_meta)

        # BM25 ranks
        for rank, (bm25_score, chunk) in enumerate(bm25_candidates, start=1):
            cid = chunk.metadata.chunk_id
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (rrf_k + rank))
            if cid not in chunk_map:
                chunk_map[cid] = chunk

        # 5. Rank fusion and cut-off
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        results: List[DocumentChunk] = []

        for cid, score in ranked:
            if score >= score_threshold and cid in chunk_map:
                results.append(chunk_map[cid])
            if len(results) >= top_k:
                break

        if not results:
            logger.debug(f"Retriever abstained: no chunks met score threshold ({score_threshold}) for query '{query[:30]}'")

        return results
