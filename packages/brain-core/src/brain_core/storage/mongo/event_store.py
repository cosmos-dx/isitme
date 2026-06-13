"""MongoDB implementation of :class:`EventStore` (collection ``events``).

Idempotent re-ingest is achieved by using the event id as the Mongo ``_id`` and
replacing on conflict. Timestamps are ISO-8601 strings (UTC), so range scans
and ordering match the SQLite backend exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from brain_core.models.events import EventType, RawEvent
from brain_core.storage import db
from brain_core.storage.base import EventStore
from brain_core.storage.mongo import make_motor_client


class MongoEventStore(EventStore):
    def __init__(self, uri: str, db_name: str, client: Any | None = None):
        self._uri = uri
        self._db_name = db_name
        self._client = client
        self._db: Any | None = None

    @property
    def _coll(self) -> Any:
        return self._db["events"]

    async def init(self) -> None:
        if self._client is None:
            self._client = make_motor_client(self._uri)
        self._db = self._client[self._db_name]
        await self._coll.create_index("timestamp")

    async def append(self, events: list[RawEvent]) -> int:
        if not events:
            return 0
        # Idempotent re-ingest: replace_one(upsert) keyed on the event id.
        for e in events:
            await self._coll.replace_one(
                {"_id": e.id},
                {
                    "_id": e.id,
                    "type": e.type.value,
                    "timestamp": db.iso(e.timestamp),
                    "source": e.source,
                    "session_id": e.session_id,
                    "url": e.url,
                    "title": e.title,
                    "content": e.content,
                    "data": e.data,
                },
                upsert=True,
            )
        return len(events)

    @staticmethod
    def _to_event(doc: dict[str, Any]) -> RawEvent:
        return RawEvent(
            id=doc["_id"],
            type=EventType(doc["type"]),
            timestamp=db.parse_iso(doc["timestamp"]),
            source=doc["source"],
            session_id=doc.get("session_id"),
            url=doc.get("url"),
            title=doc.get("title"),
            content=doc.get("content"),
            data=doc.get("data") or {},
        )

    async def count(self) -> int:
        return int(await self._coll.count_documents({}))

    async def recent(self, limit: int = 100) -> list[RawEvent]:
        cursor = self._coll.find().sort("timestamp", -1).limit(limit)
        return [self._to_event(doc) async for doc in cursor]

    async def since(self, since: datetime, limit: int = 1000) -> list[RawEvent]:
        cursor = (
            self._coll.find({"timestamp": {"$gte": db.iso(since)}})
            .sort("timestamp", 1)
            .limit(limit)
        )
        return [self._to_event(doc) async for doc in cursor]

    async def prune_before(self, cutoff: datetime) -> int:
        result = await self._coll.delete_many({"timestamp": {"$lt": db.iso(cutoff)}})
        return int(result.deleted_count or 0)

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
