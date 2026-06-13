"""MongoDB implementation of :class:`GraphStore`.

Nodes live in ``graph_nodes`` (unique on ``(type, key)``), edges in
``graph_edges`` (unique on ``(src, dst, relation)``, indexed on ``src``), and
traces in ``traces`` (indexed on ``session_id``). Edge weights use the exact
same time-decay math as the SQLite backend (see :mod:`brain_core.engine.decay`):
the raw ``weight`` is the effective weight at ``last_seen`` and is decayed to
"now" on read / re-strengthened on each observation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from brain_core.engine.decay import effective_weight, reinforce, utcnow
from brain_core.models.graph import Edge, Node, NodeType, RelationType, Trace
from brain_core.storage import db
from brain_core.storage.base import GraphStore
from brain_core.storage.mongo import make_motor_client


class MongoGraphStore(GraphStore):
    def __init__(
        self,
        uri: str,
        db_name: str,
        half_life_days: float = 30.0,
        client: Any | None = None,
    ):
        self._uri = uri
        self._db_name = db_name
        self._half_life = half_life_days
        self._client = client
        self._db: Any | None = None

    @property
    def _nodes(self) -> Any:
        return self._db["graph_nodes"]

    @property
    def _edges(self) -> Any:
        return self._db["graph_edges"]

    @property
    def _traces(self) -> Any:
        return self._db["traces"]

    async def init(self) -> None:
        if self._client is None:
            self._client = make_motor_client(self._uri)
        self._db = self._client[self._db_name]
        await self._nodes.create_index([("type", 1), ("key", 1)], unique=True)
        await self._edges.create_index(
            [("src", 1), ("dst", 1), ("relation", 1)], unique=True
        )
        await self._edges.create_index("src")
        await self._traces.create_index("session_id")

    @staticmethod
    def _to_node(doc: dict[str, Any]) -> Node:
        return Node(
            id=doc["_id"],
            type=NodeType(doc["type"]),
            key=doc["key"],
            label=doc["label"],
            weight=doc["weight"],
            attributes=doc.get("attributes") or {},
            created_at=db.parse_iso(doc["created_at"]),
            updated_at=db.parse_iso(doc["updated_at"]),
        )

    @staticmethod
    def _to_edge(doc: dict[str, Any]) -> Edge:
        return Edge(
            id=doc["_id"],
            src=doc["src"],
            dst=doc["dst"],
            relation=RelationType(doc["relation"]),
            weight=doc["weight"],
            last_seen=db.parse_iso(doc["last_seen"]),
            created_at=db.parse_iso(doc["created_at"]),
            attributes=doc.get("attributes") or {},
        )

    async def upsert_node(
        self,
        type: NodeType,
        key: str,
        label: str,
        weight_delta: float = 0.0,
        attributes: dict | None = None,
    ) -> Node:
        now = utcnow()
        existing = await self._nodes.find_one({"type": type.value, "key": key})
        if existing is None:
            node = Node(
                type=type,
                key=key,
                label=label,
                weight=weight_delta,
                attributes=attributes or {},
                created_at=now,
                updated_at=now,
            )
            await self._nodes.insert_one(
                {
                    "_id": node.id,
                    "type": node.type.value,
                    "key": node.key,
                    "label": node.label,
                    "weight": node.weight,
                    "attributes": node.attributes,
                    "created_at": db.iso(node.created_at),
                    "updated_at": db.iso(node.updated_at),
                }
            )
            return node
        merged_attrs = {**(existing.get("attributes") or {}), **(attributes or {})}
        new_weight = existing["weight"] + weight_delta
        await self._nodes.update_one(
            {"_id": existing["_id"]},
            {"$set": {"weight": new_weight, "attributes": merged_attrs, "updated_at": db.iso(now)}},
        )
        node = self._to_node(existing)
        node.weight = new_weight
        node.attributes = merged_attrs
        node.updated_at = now
        return node

    async def get_node(self, node_id: str) -> Node | None:
        doc = await self._nodes.find_one({"_id": node_id})
        return self._to_node(doc) if doc else None

    async def find_node(self, type: NodeType, key: str) -> Node | None:
        doc = await self._nodes.find_one({"type": type.value, "key": key})
        return self._to_node(doc) if doc else None

    async def observe_edge(
        self,
        src_id: str,
        dst_id: str,
        relation: RelationType,
        weight_delta: float = 1.0,
        at: datetime | None = None,
        attributes: dict | None = None,
    ) -> Edge:
        now = at or utcnow()
        existing = await self._edges.find_one(
            {"src": src_id, "dst": dst_id, "relation": relation.value}
        )
        if existing is None:
            edge = Edge(
                src=src_id,
                dst=dst_id,
                relation=relation,
                weight=weight_delta,
                last_seen=now,
                created_at=now,
                attributes=attributes or {},
            )
            await self._edges.insert_one(
                {
                    "_id": edge.id,
                    "src": edge.src,
                    "dst": edge.dst,
                    "relation": edge.relation.value,
                    "weight": edge.weight,
                    "last_seen": db.iso(edge.last_seen),
                    "created_at": db.iso(edge.created_at),
                    "attributes": edge.attributes,
                }
            )
            edge.effective_weight = edge.weight
            return edge
        new_weight = reinforce(
            existing["weight"],
            db.parse_iso(existing["last_seen"]),
            weight_delta,
            now,
            self._half_life,
        )
        merged_attrs = {**(existing.get("attributes") or {}), **(attributes or {})}
        await self._edges.update_one(
            {"_id": existing["_id"]},
            {"$set": {"weight": new_weight, "last_seen": db.iso(now), "attributes": merged_attrs}},
        )
        edge = self._to_edge(existing)
        edge.weight = new_weight
        edge.last_seen = now
        edge.attributes = merged_attrs
        edge.effective_weight = new_weight
        return edge

    async def neighbors(
        self,
        node_id: str,
        relation: RelationType | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[tuple[Edge, Node]]:
        now = now or utcnow()
        query: dict[str, Any] = {"src": node_id}
        if relation is not None:
            query["relation"] = relation.value
        edge_docs = [doc async for doc in self._edges.find(query)]
        dst_ids = list({doc["dst"] for doc in edge_docs})
        node_docs = {
            doc["_id"]: doc async for doc in self._nodes.find({"_id": {"$in": dst_ids}})
        }
        out: list[tuple[Edge, Node]] = []
        for doc in edge_docs:
            target = node_docs.get(doc["dst"])
            if target is None:
                continue
            edge = self._to_edge(doc)
            edge.effective_weight = effective_weight(
                edge.weight, edge.last_seen, now, self._half_life
            )
            out.append((edge, self._to_node(target)))
        out.sort(key=lambda pair: pair[0].effective_weight or 0.0, reverse=True)
        return out[:limit]

    async def top_nodes(self, type: NodeType | None = None, limit: int = 20) -> list[Node]:
        query: dict[str, Any] = {}
        if type is not None:
            query["type"] = type.value
        cursor = self._nodes.find(query).sort("weight", -1).limit(limit)
        return [self._to_node(doc) async for doc in cursor]

    async def dump_graph(
        self, node_limit: int = 1500, edge_limit: int = 4000
    ) -> tuple[list[Node], list[Edge]]:
        now = utcnow()
        node_cursor = self._nodes.find().sort("weight", -1).limit(node_limit)
        nodes = [self._to_node(doc) async for doc in node_cursor]
        node_ids = {n.id for n in nodes}
        edge_cursor = self._edges.find().sort("weight", -1).limit(edge_limit)
        edges: list[Edge] = []
        async for doc in edge_cursor:
            if doc["src"] not in node_ids or doc["dst"] not in node_ids:
                continue
            edge = self._to_edge(doc)
            edge.effective_weight = effective_weight(
                edge.weight, edge.last_seen, now, self._half_life
            )
            edges.append(edge)
        return nodes, edges

    async def add_trace(self, trace: Trace) -> None:
        await self._traces.insert_one(
            {
                "_id": trace.id,
                "session_id": trace.session_id,
                "node_ids": trace.node_ids,
                "started_at": db.iso(trace.started_at),
                "ended_at": db.iso(trace.ended_at),
                "attributes": trace.attributes,
            }
        )

    async def recent_traces(self, limit: int = 20) -> list[Trace]:
        cursor = self._traces.find().sort("started_at", -1).limit(limit)
        return [
            Trace(
                id=doc["_id"],
                session_id=doc["session_id"],
                node_ids=doc.get("node_ids") or [],
                started_at=db.parse_iso(doc["started_at"]),
                ended_at=db.parse_iso(doc["ended_at"]),
                attributes=doc.get("attributes") or {},
            )
            async for doc in cursor
        ]

    async def node_count(self) -> int:
        return int(await self._nodes.count_documents({}))

    async def edge_count(self) -> int:
        return int(await self._edges.count_documents({}))

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
