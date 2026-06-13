"""Embedding providers behind a single ABC."""

from brain_core.embeddings.base import EmbeddingProvider
from brain_core.embeddings.hashing import HashingEmbeddingProvider

__all__ = ["EmbeddingProvider", "HashingEmbeddingProvider"]
