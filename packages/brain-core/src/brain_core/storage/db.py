"""SQLAlchemy Core schema + async engine helpers for the default backends.

We use SQLAlchemy Core (not the ORM) for explicit, async-friendly queries. The
same schema works on SQLite (default) and Postgres (drop-in via DSN), which is
why the event/graph stores share this module. Timestamps are stored as ISO-8601
TEXT to keep timezone handling deterministic across SQLite and Postgres.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

metadata = sa.MetaData()

events_table = sa.Table(
    "events",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("type", sa.String, nullable=False),
    sa.Column("timestamp", sa.String, nullable=False, index=True),
    sa.Column("source", sa.String, nullable=False, default="unknown"),
    sa.Column("session_id", sa.String, nullable=True),
    sa.Column("url", sa.String, nullable=True),
    sa.Column("title", sa.String, nullable=True),
    sa.Column("content", sa.Text, nullable=True),
    sa.Column("data", sa.JSON, nullable=False, default=dict),
)

nodes_table = sa.Table(
    "nodes",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("type", sa.String, nullable=False),
    sa.Column("key", sa.String, nullable=False),
    sa.Column("label", sa.String, nullable=False),
    sa.Column("weight", sa.Float, nullable=False, default=0.0),
    sa.Column("attributes", sa.JSON, nullable=False, default=dict),
    sa.Column("created_at", sa.String, nullable=False),
    sa.Column("updated_at", sa.String, nullable=False),
    sa.UniqueConstraint("type", "key", name="uq_node_type_key"),
)

edges_table = sa.Table(
    "edges",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("src", sa.String, nullable=False, index=True),
    sa.Column("dst", sa.String, nullable=False),
    sa.Column("relation", sa.String, nullable=False),
    sa.Column("weight", sa.Float, nullable=False, default=0.0),
    sa.Column("last_seen", sa.String, nullable=False),
    sa.Column("created_at", sa.String, nullable=False),
    sa.Column("attributes", sa.JSON, nullable=False, default=dict),
    sa.UniqueConstraint("src", "dst", "relation", name="uq_edge_triple"),
)

traces_table = sa.Table(
    "traces",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("session_id", sa.String, nullable=False, index=True),
    sa.Column("node_ids", sa.JSON, nullable=False, default=list),
    sa.Column("started_at", sa.String, nullable=False),
    sa.Column("ended_at", sa.String, nullable=False),
    sa.Column("attributes", sa.JSON, nullable=False, default=dict),
)

outbox_table = sa.Table(
    "outbox",
    metadata,
    sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("op", sa.String, nullable=False),
    sa.Column("payload", sa.JSON, nullable=False),
    sa.Column("status", sa.String, nullable=False, default="pending", index=True),
    sa.Column("created_at", sa.String, nullable=False),
)


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True)


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
