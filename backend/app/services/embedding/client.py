"""
Embedding client — local sentence-transformers model for the platform.

Spec: EM-001, EM-002, EM-003
- Model: BAAI/bge-large-en-v1.5 (1024 dim), runs in-process — no API key, no cost
- Input types: "document" for stored content, "query" for retrieval queries
  (bge models expect a retrieval instruction prefix on queries)
- Vectors are L2-normalised, so cosine similarity == dot product

The model (~1.3 GB) is downloaded from Hugging Face on first use and cached
in ~/.cache/huggingface. Loading is lazy so API startup and tests that never
embed don't pay the cost. encode() runs in a worker thread to keep the event
loop free.

Dimension note: the original spec targeted 1536 (vector(1536) in migration
0001); migration 0004 resizes the pgvector columns to the actual bge-large
dimension (1024).
"""

from __future__ import annotations

import json
import os
import asyncio
import threading
from typing import Any, Literal

from app.core.logging import get_logger

log = get_logger(__name__)

_EMBEDDING_MODEL = "BAAI/bge-large-en-v1.5"
_EMBEDDING_DIM = 1024
_BATCH_SIZE = 32
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

InputType = Literal["document", "query"]


class EmbeddingClient:
    """Async wrapper around a local sentence-transformers embedding model."""

    def __init__(self) -> None:
        self._model: Any = None
        self._load_lock = threading.Lock()
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            log.warning("embedding.no_sentence_transformers",
                        hint="pip install sentence-transformers to enable embeddings")

    def _get_model(self) -> Any:
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    try:
                        from sentence_transformers import SentenceTransformer
                    except ImportError as exc:
                        raise RuntimeError(
                            "sentence-transformers is not installed — embeddings are unavailable"
                        ) from exc
                    # Force CPU by default: Celery prefork workers fork(), and
                    # PyTorch's Apple-Metal (MPS) backend can't reach the Metal
                    # compiler service in a forked child ("Unable to reach
                    # MTLCompilerService"), which crashes embedding. CPU is plenty
                    # for this model/scale. Override with EMBEDDING_DEVICE=mps|cuda.
                    device = os.getenv("EMBEDDING_DEVICE", "cpu")
                    log.info("embedding.loading_model", model=_EMBEDDING_MODEL, device=device)
                    self._model = SentenceTransformer(_EMBEDDING_MODEL, device=device)
                    log.info("embedding.model_loaded", model=_EMBEDDING_MODEL, device=device)
        return self._model

    async def embed_texts(
        self,
        texts: list[str],
        input_type: InputType = "document",
    ) -> list[list[float]]:
        """
        Embed a list of texts. Returns list of float vectors.
        Raises RuntimeError if the embedding model is unavailable.
        """
        if not texts:
            return []
        return await asyncio.to_thread(self._encode, texts, input_type)

    async def embed_single(
        self,
        text: str,
        input_type: InputType = "query",
    ) -> list[float]:
        """Embed a single text (query mode by default)."""
        vectors = await self.embed_texts([text], input_type)
        return vectors[0]

    def _encode(self, texts: list[str], input_type: InputType) -> list[list[float]]:
        model = self._get_model()
        if input_type == "query":
            texts = [_QUERY_PREFIX + t for t in texts]
        embeddings = model.encode(
            texts,
            batch_size=_BATCH_SIZE,
            normalize_embeddings=True,
        )
        return [vec.tolist() for vec in embeddings]

    @property
    def dimension(self) -> int:
        return _EMBEDDING_DIM


def vector_to_json(vec: list[float]) -> str:
    """Serialize a vector to JSON for storage in the Text embedding column."""
    return json.dumps(vec)


def json_to_vector(text: str) -> list[float]:
    """Deserialize a JSON-stored embedding back to floats."""
    return json.loads(text)


_client_instance: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _client_instance
    if _client_instance is None:
        _client_instance = EmbeddingClient()
    return _client_instance
