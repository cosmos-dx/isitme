"""SQLite-backed ``OutboxStore`` — the durable queue behind the OUTBOX pattern.

Every local write that should eventually reach the cloud is enqueued here in
the same logical flow as the local commit. A separate sync worker drains it,
so local writes never block on (and never lose data to) network availability.
"""

from __future__ import annotations

import sqlalchemy as sa

from brain_core.engine.decay import utcnow
from brain_core.storage import db
from brain_core.storage.base import OutboxStore


class SqlOutboxStore(OutboxStore):
    def __init__(self, url: str):
        self._engine = db.make_engine(url)

    async def init(self) -> None:
        await db.create_all(self._engine)

    async def enqueue(self, op: str, payload: dict) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                db.outbox_table.insert().values(
                    op=op, payload=payload, status="pending", created_at=db.iso(utcnow())
                )
            )

    async def pending(self, limit: int = 100) -> list[tuple[int, str, dict]]:
        stmt = (
            sa.select(db.outbox_table)
            .where(db.outbox_table.c.status == "pending")
            .order_by(db.outbox_table.c.row_id.asc())
            .limit(limit)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(stmt)).mappings().all()
        return [(m["row_id"], m["op"], m["payload"] or {}) for m in rows]

    async def mark_sent(self, row_ids: list[int]) -> None:
        if not row_ids:
            return
        async with self._engine.begin() as conn:
            await conn.execute(
                db.outbox_table.update()
                .where(db.outbox_table.c.row_id.in_(row_ids))
                .values(status="sent")
            )

    async def pending_count(self) -> int:
        async with self._engine.connect() as conn:
            return int(
                (
                    await conn.execute(
                        sa.select(sa.func.count())
                        .select_from(db.outbox_table)
                        .where(db.outbox_table.c.status == "pending")
                    )
                ).scalar_one()
            )

    async def close(self) -> None:
        await self._engine.dispose()
