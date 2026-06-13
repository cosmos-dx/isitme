"""Construct concrete backends from ``Settings``.

This is the single place that maps config -> implementations, so the rest of
the code depends only on the ABCs. Adding a new backend means adding a branch
here (and the impl), nothing else.
"""

from __future__ import annotations

from brain_core.config import Settings
from brain_core.embeddings.base import EmbeddingProvider
from brain_core.embeddings.hashing import HashingEmbeddingProvider
from brain_core.storage.base import EventStore, GraphStore, OutboxStore, VectorStore
from brain_core.storage.sqlite_event_store import SqlEventStore
from brain_core.storage.sqlite_graph_store import SqlGraphStore
from brain_core.storage.sqlite_outbox import SqlOutboxStore
from brain_core.storage.vector.numpy_store import NumpyVectorStore


def build_event_store(settings: Settings) -> EventStore:
    # SqlEventStore is dialect-agnostic; a postgres DSN is a drop-in.
    return SqlEventStore(settings.event_db_url)


def build_graph_store(settings: Settings) -> GraphStore:
    backend = settings.storage.graph_backend
    if backend in ("sqlite",) or settings.storage.postgres_dsn:
        return SqlGraphStore(settings.graph_db_url, settings.graph.edge_half_life_days)
    # TODO(scale): Neo4j / Kùzu adapters implementing GraphStore.
    raise NotImplementedError(
        f"graph_backend={backend!r} not bundled. Implement a GraphStore adapter "
        "(see README 'Scaling the graph') or use the default 'sqlite'."
    )


def build_vector_store(settings: Settings) -> VectorStore:
    backend = settings.storage.vector_backend
    if backend == "numpy":
        return NumpyVectorStore(settings.data_path / "vectors")
    if backend == "chroma":
        from brain_core.storage.vector.chroma_store import ChromaVectorStore

        return ChromaVectorStore(settings.storage.chroma_path or str(settings.data_path / "chroma"))
    # TODO(scale): Qdrant / pgvector adapters implementing VectorStore.
    raise NotImplementedError(
        f"vector_backend={backend!r} not bundled. Use 'numpy' (default) or 'chroma'."
    )


def build_outbox(settings: Settings) -> OutboxStore:
    return SqlOutboxStore(settings.event_db_url)


def build_embeddings(settings: Settings) -> EmbeddingProvider:
    provider = settings.embedding.provider
    if provider == "hashing":
        return HashingEmbeddingProvider(settings.embedding.dim)
    if provider == "sentence_transformers":
        from brain_core.embeddings.sentence_transformer import (
            SentenceTransformerEmbeddingProvider,
        )

        return SentenceTransformerEmbeddingProvider(settings.embedding.st_model)
    if provider == "openai":
        from brain_core.embeddings.openai_provider import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            settings.embedding.openai_model, settings.embedding.openai_api_key
        )
    raise NotImplementedError(f"embedding provider {provider!r} not supported.")
