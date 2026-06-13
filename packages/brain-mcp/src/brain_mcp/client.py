"""Async HTTP client for the isitme Web API / BFF.

Wraps the API-key-authenticated endpoints the MCP tools need and translates
transport/HTTP failures into a small set of typed, actionable exceptions so the
server can return clear guidance to the calling LLM.
"""

from __future__ import annotations

from typing import Any

import httpx

from brain_mcp import __version__


class BrainAPIError(RuntimeError):
    """Base class for all Brain API failures surfaced to the caller."""


class BrainAuthError(BrainAPIError):
    """The configured ``X-API-Key`` was rejected (401/403)."""


class BrainUnreachableError(BrainAPIError):
    """The Web API could not be reached (connection/timeout)."""


class BrainResponseError(BrainAPIError):
    """The Web API returned an unexpected (non-2xx) response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BrainClient:
    """Thin async client over the isitme Web API.

    All requests carry the ``X-API-Key`` header. The instance owns a single
    :class:`httpx.AsyncClient`; call :meth:`aclose` (or use it as an async
    context manager) to release the connection pool.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={
                "X-API-Key": api_key,
                "User-Agent": f"brain-mcp/{__version__}",
                "Accept": "application/json",
            },
        )

    async def __aenter__(self) -> BrainClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # --- low-level request helper ------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            resp = await self._client.request(method, path, json=json, params=params)
        except httpx.TimeoutException as exc:
            raise BrainUnreachableError(
                f"Timed out talking to the brain at {self._base_url}. "
                "Is the isitme Web API running?"
            ) from exc
        except httpx.HTTPError as exc:
            raise BrainUnreachableError(
                f"Could not reach the brain at {self._base_url} ({exc.__class__.__name__}). "
                "Start the isitme Web API (default port 5050) and try again."
            ) from exc

        if resp.status_code in (401, 403):
            raise BrainAuthError(
                "The brain rejected the configured API key (HTTP "
                f"{resp.status_code}). Generate a fresh key in the isitme dashboard "
                "and update BRAIN_API_KEY in your MCP client config."
            )
        if resp.status_code >= 400:
            raise BrainResponseError(
                f"Brain API error on {method} {path}: HTTP {resp.status_code} "
                f"{_safe_detail(resp)}",
                status_code=resp.status_code,
            )
        return _safe_json(resp)

    # --- endpoints ----------------------------------------------------------
    async def validate_key(self) -> dict[str, Any]:
        """Verify the configured key. Raises :class:`BrainAuthError` if invalid."""
        result = await self._request("GET", "/api/keys/validate")
        return result if isinstance(result, dict) else {"valid": True, "raw": result}

    async def recall(self, query: str, k: int = 5) -> Any:
        return await self._request("POST", "/api/recall", json={"query": query, "k": k})

    async def search(self, query: str, k: int = 8) -> Any:
        return await self._request("POST", "/api/search", json={"query": query, "k": k})

    async def profile(self) -> Any:
        return await self._request("GET", "/api/profile")

    async def ask(self, question: str, k: int = 6) -> Any:
        return await self._request("POST", "/api/ask", json={"question": question, "k": k})

    async def log(self, event: dict[str, Any]) -> Any:
        return await self._request("POST", "/api/log", json=event)

    async def stats(self) -> Any:
        return await self._request("GET", "/api/stats")


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}


def _safe_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:200]
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])[:200]
    return str(body)[:200]
