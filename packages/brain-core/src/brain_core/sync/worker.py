"""Sync worker — drains the outbox to the cloud client on an interval.

Runnable standalone (``python -m brain_core.sync.worker``) or embedded as an
asyncio task. Each pending row is encrypted (when a key is configured) and
pushed in batches; only on success are rows marked sent, so failures are
retried and nothing is lost.
"""

from __future__ import annotations

import asyncio
import logging

from brain_core.config import Settings, load_settings
from brain_core.storage.base import OutboxStore
from brain_core.storage.sqlite_outbox import SqlOutboxStore
from brain_core.sync.cloud_client import CloudClient, HttpCloudClient, NoopCloudClient
from brain_core.sync.crypto import PayloadCipher, load_or_create_key

logger = logging.getLogger("brain.sync")


class SyncWorker:
    def __init__(
        self,
        outbox: OutboxStore,
        client: CloudClient,
        cipher: PayloadCipher | None,
        interval_seconds: int = 30,
        batch_size: int = 100,
    ):
        self._outbox = outbox
        self._client = client
        self._cipher = cipher
        self._interval = interval_seconds
        self._batch = batch_size
        self._stop = asyncio.Event()

    async def drain_once(self) -> int:
        pending = await self._outbox.pending(self._batch)
        if not pending:
            return 0
        records = []
        for row_id, op, payload in pending:
            body = {"op": op, "payload": payload}
            record = {
                "id": row_id,
                "encrypted": self._cipher is not None,
                "data": self._cipher.encrypt(body) if self._cipher else body,
            }
            records.append(record)
        if await self._client.push(records):
            await self._outbox.mark_sent([r["id"] for r in records])
            logger.info("Synced %d outbox record(s).", len(records))
            return len(records)
        return 0

    async def run(self) -> None:
        logger.info("Sync worker started (interval=%ss).", self._interval)
        while not self._stop.is_set():
            try:
                await self.drain_once()
            except Exception:  # pragma: no cover - keep worker alive
                logger.exception("Sync iteration failed.")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()


def build_worker(settings: Settings) -> SyncWorker:
    outbox = SqlOutboxStore(settings.event_db_url)
    if settings.mode == "cloud_sync" and settings.cloud.endpoint:
        client: CloudClient = HttpCloudClient(settings.cloud.endpoint, settings.cloud.api_key)
        key = load_or_create_key(settings.cloud.encryption_key, settings.data_path)
        cipher: PayloadCipher | None = PayloadCipher(key)
    else:
        client = NoopCloudClient()
        cipher = None
    return SyncWorker(
        outbox,
        client,
        cipher,
        settings.cloud.sync_interval_seconds,
        settings.cloud.batch_size,
    )


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    worker = build_worker(settings)
    await worker._outbox.init()
    await worker.run()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
