"""Cloud client interface for the optional sync backend.

The Core Brain is the only stateful service; the cloud is an *optional* mirror
used for online search and multi-device recall. This module defines the
contract (``CloudClient``) and ships two implementations:

* ``NoopCloudClient``  — default; logs and discards (keeps everything local).
* ``HttpCloudClient``  — POSTs encrypted records to a cloud endpoint.

A full server-side cloud is intentionally out of scope here.
TODO(cloud): implement the receiving service (auth, storage, online search).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger("brain.sync")


class CloudClient(ABC):
    @abstractmethod
    async def push(self, records: list[dict]) -> bool:
        """Push a batch of (already-encrypted) outbox records. Returns success."""

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None


class NoopCloudClient(CloudClient):
    """Default: pretend to sync, but keep all data local."""

    async def push(self, records: list[dict]) -> bool:
        logger.info("NoopCloudClient: dropping %d record(s) (local-only mode).", len(records))
        return True


class HttpCloudClient(CloudClient):
    def __init__(self, endpoint: str, api_key: str | None = None, timeout: float = 10.0):
        self._endpoint = endpoint.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def push(self, records: list[dict]) -> bool:
        try:
            resp = await self._client.post(f"{self._endpoint}/v1/sync", json={"records": records})
            resp.raise_for_status()
            return True
        except httpx.HTTPError as exc:  # pragma: no cover - network path
            logger.warning("Cloud push failed (will retry later): %s", exc)
            return False

    async def close(self) -> None:
        await self._client.aclose()
