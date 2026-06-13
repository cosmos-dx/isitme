"""SQLite (SQLAlchemy async) implementation of ``GraphStore``.

This is the default embedded knowledge-graph backend. It stores typed nodes,
weighted edges, and traces in plain relational tables, computing time-decayed
edge weights on read. For larger graphs / native traversal, swap in Neo4j or
Kùzu behind the same ``GraphStore`` ABC (see README "Scaling the graph").
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from brain_core.engine.decay import effective_weight, reinforce, utcnow
from brain_core.models.graph import Edge, Node, NodeType, RelationType, Trace
from brain_core.storage import db
from brain_core.storage.base import GraphStore


class SqlGraphStore(GraphStore):
    def __init__(self, url: str, half_life_days: float = 30.0):
        self._engine = db.make_engine(url)
        self._half_life = half_life_days

    async def init(self) -> None:
        await db.create_all(self._engine)

    @staticmethod
    def _row_to_node(m) -> Node:
        return Node(
            id=m["id"],
            type=NodeType(m["type"]),
            key=m["key"],
            label=m["label"],
            weight=m["weight"],
            attributes=m["attributes"] or {},
            created_at=db.parse_iso(m["created_at"]),
            updated_at=db.parse_iso(m["updated_at"]),
        )

    @staticmethod
    def _row_to_edge(m) -> Edge:
        return Edge(
            id=m["id"],
            src=m["src"],
            dst=m["dst"],
            relation=RelationType(m["relation"]),
            weight=m["weight"],
            last_seen=db.parse_iso(m["last_seen"]),
            created_at=db.parse_iso(m["created_at"]),
            attributes=m["attributes"] or {},
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
        async with self._engine.begin() as conn:
            existing = (
                await conn.execute(
                    sa.select(db.nodes_table).where(
                        db.nodes_table.c.type == type.value,
                        db.nodes_table.c.key == key,
                    )
                )
            ).first()
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
                await conn.execute(
                    db.nodes_table.insert().values(
                        id=node.id,
                        type=node.type.value,
                        key=node.key,
                        label=node.label,
                        weight=node.weight,
                        attributes=node.attributes,
                        created_at=db.iso(node.created_at),
                        updated_at=db.iso(node.updated_at),
                    )
                )
                return node
            m = existing._mapping
            merged_attrs = {**(m["attributes"] or {}), **(attributes or {})}
            new_weight = m["weight"] + weight_delta
            await conn.execute(
                db.nodes_table.update()
                .where(db.nodes_table.c.id == m["id"])
                .values(weight=new_weight, attributes=merged_attrs, updated_at=db.iso(now))
            )
            node = self._row_to_node(m)
            node.weight = new_weight
            node.attributes = merged_attrs
            node.updated_at = now
            return node

    async def get_node(self, node_id: str) -> Node | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.select(db.nodes_table).where(db.nodes_table.c.id == node_id)
                )
            ).first()
            return self._row_to_node(row._mapping) if row else None

    async def find_node(self, type: NodeType, key: str) -> Node | None:
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.select(db.nodes_table).where(
                        db.nodes_table.c.type == type.value,
                        db.nodes_table.c.key == key,
                    )
                )
            ).first()
            return self._row_to_node(row._mapping) if row else None

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
        async with self._engine.begin() as conn:
            existing = (
                await conn.execute(
                    sa.select(db.edges_table).where(
                        db.edges_table.c.src == src_id,
                        db.edges_table.c.dst == dst_id,
                        db.edges_table.c.relation == relation.value,
                    )
                )
            ).first()
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
                await conn.execute(
                    db.edges_table.insert().values(
                        id=edge.id,
                        src=edge.src,
                        dst=edge.dst,
                        relation=edge.relation.value,
                        weight=edge.weight,
                        last_seen=db.iso(edge.last_seen),
                        created_at=db.iso(edge.created_at),
                        attributes=edge.attributes,
                    )
                )
                edge.effective_weight = edge.weight
                return edge
            m = existing._mapping
            new_weight = reinforce(
                m["weight"], db.parse_iso(m["last_seen"]), weight_delta, now, self._half_life
            )
            merged_attrs = {**(m["attributes"] or {}), **(attributes or {})}
            await conn.execute(
                db.edges_table.update()
                .where(db.edges_table.c.id == m["id"])
                .values(weight=new_weight, last_seen=db.iso(now), attributes=merged_attrs)
            )
            edge = self._row_to_edge(m)
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
        e = db.edges_table
        n = db.nodes_table.alias("n")
        conds = [e.c.src == node_id]
        if relation is not None:
            conds.append(e.c.relation == relation.value)
        stmt = (
            sa.select(
                e.c.id.label("e_id"),
                e.c.src.label("e_src"),
                e.c.dst.label("e_dst"),
                e.c.relation.label("e_relation"),
                e.c.weight.label("e_weight"),
                e.c.last_seen.label("e_last_seen"),
                e.c.created_at.label("e_created_at"),
                e.c.attributes.label("e_attributes"),
                n.c.id.label("n_id"),
                n.c.type.label("n_type"),
                n.c.key.label("n_key"),
                n.c.label.label("n_label"),
                n.c.weight.label("n_weight"),
                n.c.attributes.label("n_attributes"),
                n.c.created_at.label("n_created_at"),
                n.c.updated_at.label("n_updated_at"),
            )
            .select_from(e.join(n, e.c.dst == n.c.id))
            .where(*conds)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        out: list[tuple[Edge, Node]] = []
        for m in rows:
            edge = Edge(
                id=m["e_id"],
                src=m["e_src"],
                dst=m["e_dst"],
                relation=RelationType(m["e_relation"]),
                weight=m["e_weight"],
                last_seen=db.parse_iso(m["e_last_seen"]),
                created_at=db.parse_iso(m["e_created_at"]),
                attributes=m["e_attributes"] or {},
            )
            edge.effective_weight = effective_weight(
                edge.weight, edge.last_seen, now, self._half_life
            )
            node = Node(
                id=m["n_id"],
                type=NodeType(m["n_type"]),
                key=m["n_key"],
                label=m["n_label"],
                weight=m["n_weight"],
                attributes=m["n_attributes"] or {},
                created_at=db.parse_iso(m["n_created_at"]),
                updated_at=db.parse_iso(m["n_updated_at"]),
            )
            out.append((edge, node))
        out.sort(key=lambda pair: pair[0].effective_weight or 0.0, reverse=True)
        return out[:limit]

    async def top_nodes(self, type: NodeType | None = None, limit: int = 20) -> list[Node]:
        stmt = sa.select(db.nodes_table)
        if type is not None:
            stmt = stmt.where(db.nodes_table.c.type == type.value)
        stmt = stmt.order_by(db.nodes_table.c.weight.desc()).limit(limit)
        async with self._engine.connect() as conn:
            result = await conn.execute(stmt)
            return [self._row_to_node(m) for m in result.mappings().all()]

    async def dump_graph(
        self, node_limit: int = 1500, edge_limit: int = 4000
    ) -> tuple[list[Node], list[Edge]]:
        now = utcnow()
        async with self._engine.connect() as conn:
            node_rows = (
                await conn.execute(
                    sa.select(db.nodes_table)
                    .order_by(db.nodes_table.c.weight.desc())
                    .limit(node_limit)
                )
            ).mappings().all()
            edge_rows = (
                await conn.execute(
                    sa.select(db.edges_table)
                    .order_by(db.edges_table.c.weight.desc())
                    .limit(edge_limit)
                )
            ).mappings().all()
        nodes = [self._row_to_node(m) for m in node_rows]
        node_ids = {n.id for n in nodes}
        edges: list[Edge] = []
        for m in edge_rows:
            if m["src"] not in node_ids or m["dst"] not in node_ids:
                continue
            edge = self._row_to_edge(m)
            edge.effective_weight = effective_weight(
                edge.weight, edge.last_seen, now, self._half_life
            )
            edges.append(edge)
        return nodes, edges

    async def add_trace(self, trace: Trace) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                db.traces_table.insert().values(
                    id=trace.id,
                    session_id=trace.session_id,
                    node_ids=trace.node_ids,
                    started_at=db.iso(trace.started_at),
                    ended_at=db.iso(trace.ended_at),
                    attributes=trace.attributes,
                )
            )

    async def recent_traces(self, limit: int = 20) -> list[Trace]:
        stmt = sa.select(db.traces_table).order_by(db.traces_table.c.started_at.desc()).limit(limit)
        async with self._engine.connect() as conn:
            result = await conn.execute(stmt)
            return [
                Trace(
                    id=m["id"],
                    session_id=m["session_id"],
                    node_ids=m["node_ids"] or [],
                    started_at=db.parse_iso(m["started_at"]),
                    ended_at=db.parse_iso(m["ended_at"]),
                    attributes=m["attributes"] or {},
                )
                for m in result.mappings().all()
            ]

    async def node_count(self) -> int:
        async with self._engine.connect() as conn:
            return int(
                (await conn.execute(sa.select(sa.func.count()).select_from(db.nodes_table)))
                .scalar_one()
            )

    async def edge_count(self) -> int:
        async with self._engine.connect() as conn:
            return int(
                (await conn.execute(sa.select(sa.func.count()).select_from(db.edges_table)))
                .scalar_one()
            )

    async def close(self) -> None:
        await self._engine.dispose()
