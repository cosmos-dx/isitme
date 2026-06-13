"""SQLite (SQLAlchemy async) implementation of ``EventStore``.

Postgres is a drop-in: pass a ``postgresql+asyncpg://`` URL — the schema and
queries here are dialect-agnostic SQLAlchemy Core.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from brain_core.models.events import EventType, RawEvent
from brain_core.storage import db
from brain_core.storage.base import EventStore


class SqlEventStore(EventStore):
    def __init__(self, url: str):
        self._engine = db.make_engine(url)

    async def init(self) -> None:
        await db.create_all(self._engine)

    async def append(self, events: list[RawEvent]) -> int:
        if not events:
            return 0
        rows = [
            {
                "id": e.id,
                "type": e.type.value,
                "timestamp": db.iso(e.timestamp),
                "source": e.source,
                "session_id": e.session_id,
                "url": e.url,
                "title": e.title,
                "content": e.content,
                "data": e.data,
            }
            for e in events
        ]
        stmt = db.events_table.insert()
        if self._is_sqlite:
            # Idempotent re-ingest: ignore duplicate event ids.
            stmt = stmt.prefix_with("OR IGNORE")
        async with self._engine.begin() as conn:
            await conn.execute(stmt, rows)
        return len(rows)

    @property
    def _is_sqlite(self) -> bool:
        return self._engine.dialect.name == "sqlite"

    def _to_event(self, row: sa.Row) -> RawEvent:
        m = row._mapping
        return RawEvent(
            id=m["id"],
            type=EventType(m["type"]),
            timestamp=db.parse_iso(m["timestamp"]),
            source=m["source"],
            session_id=m["session_id"],
            url=m["url"],
            title=m["title"],
            content=m["content"],
            data=m["data"] or {},
        )

    async def count(self) -> int:
        async with self._engine.connect() as conn:
            result = await conn.execute(sa.select(sa.func.count()).select_from(db.events_table))
            return int(result.scalar_one())

    async def recent(self, limit: int = 100) -> list[RawEvent]:
        stmt = sa.select(db.events_table).order_by(db.events_table.c.timestamp.desc()).limit(limit)
        async with self._engine.connect() as conn:
            result = await conn.execute(stmt)
            return [self._to_event(r) for r in result]

    async def since(self, since: datetime, limit: int = 1000) -> list[RawEvent]:
        stmt = (
            sa.select(db.events_table)
            .where(db.events_table.c.timestamp >= db.iso(since))
            .order_by(db.events_table.c.timestamp.asc())
            .limit(limit)
        )
        async with self._engine.connect() as conn:
            result = await conn.execute(stmt)
            return [self._to_event(r) for r in result]

    async def prune_before(self, cutoff: datetime) -> int:
        stmt = db.events_table.delete().where(db.events_table.c.timestamp < db.iso(cutoff))
        async with self._engine.begin() as conn:
            result = await conn.execute(stmt)
            return result.rowcount or 0

    async def close(self) -> None:
        await self._engine.dispose()
