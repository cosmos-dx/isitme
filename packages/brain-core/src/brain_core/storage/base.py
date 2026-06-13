"""Abstract base classes for every pluggable storage backend.

These ABCs are the contract that makes the system scalable: the brain, API,
and engine depend only on these interfaces, never on a concrete backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from brain_core.models.events import RawEvent
from brain_core.models.graph import Edge, Node, NodeType, RelationType, Trace


class EventStore(ABC):
    """Append-only log of raw (already-redacted) events."""

    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def append(self, events: list[RawEvent]) -> int:
        """Persist events; returns the number written."""

    @abstractmethod
    async def count(self) -> int: ...

    @abstractmethod
    async def recent(self, limit: int = 100) -> list[RawEvent]: ...

    @abstractmethod
    async def since(self, since: datetime, limit: int = 1000) -> list[RawEvent]: ...

    @abstractmethod
    async def prune_before(self, cutoff: datetime) -> int:
        """Delete events older than ``cutoff`` (retention). Returns count removed."""

    @abstractmethod
    async def close(self) -> None: ...


class GraphStore(ABC):
    """Typed knowledge graph with weighted, time-decaying edges and traces."""

    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def upsert_node(
        self,
        type: NodeType,
        key: str,
        label: str,
        weight_delta: float = 0.0,
        attributes: dict | None = None,
    ) -> Node:
        """Create or update a node (deduped on ``(type, key)``)."""

    @abstractmethod
    async def get_node(self, node_id: str) -> Node | None: ...

    @abstractmethod
    async def find_node(self, type: NodeType, key: str) -> Node | None: ...

    @abstractmethod
    async def observe_edge(
        self,
        src_id: str,
        dst_id: str,
        relation: RelationType,
        weight_delta: float = 1.0,
        at: datetime | None = None,
        attributes: dict | None = None,
    ) -> Edge:
        """Strengthen (or create) an edge, decaying its prior weight to ``at``."""

    @abstractmethod
    async def neighbors(
        self,
        node_id: str,
        relation: RelationType | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[tuple[Edge, Node]]:
        """Outgoing edges + target nodes, sorted by effective (decayed) weight."""

    @abstractmethod
    async def top_nodes(
        self, type: NodeType | None = None, limit: int = 20
    ) -> list[Node]: ...

    async def dump_graph(
        self, node_limit: int = 1500, edge_limit: int = 4000
    ) -> tuple[list[Node], list[Edge]]:
        """Read-only export of the heaviest nodes + the edges between them.

        Returns nodes (with cumulative weight) and edges (with their
        time-decayed ``effective_weight`` populated). Intended for read-only
        visualization/exports; not part of the hot ingest/query path. Backends
        may override; the default raises if unsupported.
        """
        raise NotImplementedError

    @abstractmethod
    async def add_trace(self, trace: Trace) -> None: ...

    @abstractmethod
    async def recent_traces(self, limit: int = 20) -> list[Trace]: ...

    @abstractmethod
    async def node_count(self) -> int: ...

    @abstractmethod
    async def edge_count(self) -> int: ...

    @abstractmethod
    async def close(self) -> None: ...


class VectorStore(ABC):
    """Semantic memory: store text+embedding, query by cosine similarity."""

    @abstractmethod
    async def init(self, dim: int) -> None: ...

    @abstractmethod
    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        texts: list[str],
        metadatas: list[dict],
    ) -> None: ...

    @abstractmethod
    async def query(
        self, embedding: list[float], k: int = 5
    ) -> list[tuple[str, float, str, dict]]:
        """Returns ``(id, score, text, metadata)`` sorted by descending score."""

    @abstractmethod
    async def count(self) -> int: ...

    @abstractmethod
    async def close(self) -> None: ...


class OutboxStore(ABC):
    """Durable queue of local writes pending (encrypted) cloud sync."""

    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def enqueue(self, op: str, payload: dict) -> None: ...

    @abstractmethod
    async def pending(self, limit: int = 100) -> list[tuple[int, str, dict]]:
        """Returns ``(row_id, op, payload)`` for undelivered rows."""

    @abstractmethod
    async def mark_sent(self, row_ids: list[int]) -> None: ...

    @abstractmethod
    async def pending_count(self) -> int: ...

    @abstractmethod
    async def close(self) -> None: ...
