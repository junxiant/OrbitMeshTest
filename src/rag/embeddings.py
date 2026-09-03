from __future__ import annotations

from typing import List

from src.core.config import EMBEDDING_MODEL_NAME, EMBEDDING_DIMENSION
from src.core.logging import logger

# Identifies which embedding model produced the vectors in a collection.
# Written into the collection's reserved meta point at ingest time and
# checked by the retriever at init so an index built with one embedder is
# never silently queried with another.
EMBEDDER_FINGERPRINT = f"{EMBEDDING_MODEL_NAME}:{EMBEDDING_DIMENSION}"


# Vectorization process
class LocalEmbedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL_NAME):
        self.model_name = model_name
        self._fastembed = self._init_embedder()

    def _init_embedder(self):
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise RuntimeError(
                "FastEmbed is not installed; dense embeddings are unavailable. "
                "Install it with 'pip install fastembed' (see requirements.txt). "
                f"Original error: {e}"
            ) from e
        try:
            model = TextEmbedding(model_name=self.model_name)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load FastEmbed model '{self.model_name}'. The model is "
                "downloaded from HuggingFace on first use; check network access, the "
                "HF cache, and that EMBEDDING_MODEL_NAME names a FastEmbed-supported "
                f"model. Original error: {e}"
            ) from e
        logger.info(f"Loaded FastEmbed model: {self.model_name}")
        return model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        embeddings = list(self._fastembed.embed(texts))
        return [e.tolist() for e in embeddings]

    def embed_query(self, text: str) -> List[float]:
        embeddings = list(self._fastembed.query_embed(text))
        return embeddings[0].tolist()

SPARSE_MODEL_NAME = "Qdrant/bm25"


class LocalSparseEmbedder:
    def __init__(self, model_name: str = SPARSE_MODEL_NAME):
        self.model_name = model_name
        self._fastembed = self._init_embedder()

    def _init_embedder(self):
        try:
            from fastembed import SparseTextEmbedding
        except ImportError as e:
            raise RuntimeError(
                "FastEmbed is not installed; sparse embeddings are unavailable. "
                f"Original error: {e}"
            ) from e
        try:
            model = SparseTextEmbedding(model_name=self.model_name)
        except Exception as e:
            raise RuntimeError(
                f"Failed to load FastEmbed sparse model '{self.model_name}'. "
                f"Original error: {e}"
            ) from e
        logger.info(f"Loaded FastEmbed sparse model: {self.model_name}")
        return model

    def embed_documents(self, texts: List[str]):
        return list(self._fastembed.embed(texts))

    def embed_query(self, text: str):
        return list(self._fastembed.query_embed(text))[0]

