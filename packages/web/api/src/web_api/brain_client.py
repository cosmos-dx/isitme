"""Thin async HTTP client for the Core Brain (read-only + ask proxy)."""

from __future__ import annotations

from typing import Any

import httpx


class BrainClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def healthz(self) -> bool:
        try:
            resp = await self._client.get("/healthz")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def stats(self) -> dict[str, Any]:
        resp = await self._client.get("/v1/stats")
        resp.raise_for_status()
        return resp.json()

    async def profile(self) -> dict[str, Any]:
        resp = await self._client.get("/v1/profile")
        resp.raise_for_status()
        return resp.json()

    async def graph(self, node_limit: int = 1500, edge_limit: int = 4000) -> dict[str, Any]:
        resp = await self._client.get(
            "/v1/graph", params={"node_limit": node_limit, "edge_limit": edge_limit}
        )
        resp.raise_for_status()
        return resp.json()

    async def ask(self, question: str, k: int = 6) -> dict[str, Any]:
        resp = await self._client.post("/v1/ask", json={"question": question, "k": k})
        resp.raise_for_status()
        return resp.json()

    async def ingest(self, batch: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post("/v1/ingest", json=batch)
        resp.raise_for_status()
        return resp.json()

    async def log_one(self, event: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post("/v1/log", json=event)
        resp.raise_for_status()
        return resp.json()

    async def recall(self, query: str, k: int = 5) -> dict[str, Any]:
        resp = await self._client.post("/v1/recall", json={"query": query, "k": k})
        resp.raise_for_status()
        return resp.json()

    async def search_memory(self, query: str, k: int = 5) -> dict[str, Any]:
        resp = await self._client.post(
            "/v1/search_memory", json={"query": query, "k": k}
        )
        resp.raise_for_status()
        return resp.json()
