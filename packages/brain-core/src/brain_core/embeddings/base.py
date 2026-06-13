"""``EmbeddingProvider`` ABC.

Implementations turn text into fixed-dim vectors for semantic memory. The
default (``HashingEmbeddingProvider``) needs no model download and no network,
guaranteeing the system runs fully offline. Swap in sentence-transformers or
OpenAI via config for higher-quality embeddings.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors of length ``dim``."""

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
