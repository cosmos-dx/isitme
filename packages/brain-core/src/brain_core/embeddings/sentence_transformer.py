"""Optional sentence-transformers embedding provider.

Requires ``pip install 'brain-core[embeddings]'``. Loaded lazily so importing
this module never forces the heavy dependency unless actually used.
"""

from __future__ import annotations

import asyncio

from brain_core.embeddings.base import EmbeddingProvider


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - optional path
            raise ImportError(
                "sentence-transformers not installed. "
                "Install with: pip install 'brain-core[embeddings]'"
            ) from exc
        self._model = SentenceTransformer(model)
        self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        def _run() -> list[list[float]]:
            arr = self._model.encode(texts, normalize_embeddings=True)
            return [row.tolist() for row in arr]

        return await asyncio.to_thread(_run)
