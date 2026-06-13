"""MongoDB storage backends (opt-in) implementing the storage ABCs.

These adapters are selected when ``storage.event_backend``/``graph_backend``/
``vector_backend`` is set to ``"mongodb"``. They use the async ``motor`` driver
and store data in the collections ``events``, ``graph_nodes``, ``graph_edges``,
``traces`` and ``vectors`` inside ``storage.mongo_db``.

Timestamps are stored as ISO-8601 strings (mirroring the SQLite backends) so
the time-decay semantics in :mod:`brain_core.engine.decay` are byte-for-byte
identical across backends. Vectors are stored as plain float arrays and queried
in-process with numpy cosine similarity; see :mod:`vector_store` for the
documented swap to Atlas ``$vectorSearch``.
"""

from __future__ import annotations

from typing import Any


def make_motor_client(uri: str) -> Any:
    """Create an ``AsyncIOMotorClient``; ``motor`` is imported lazily."""
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError as exc:  # pragma: no cover - optional path
        raise ImportError(
            "motor not installed. Install with: pip install 'brain-core[mongo]'"
        ) from exc
    return AsyncIOMotorClient(uri)
