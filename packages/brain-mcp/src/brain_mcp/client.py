"""Async HTTP client for the isitme Web API / BFF.

Wraps the endpoints the MCP tools need and translates transport/HTTP failures
into a small set of typed, actionable exceptions so the server can return clear
guidance to the calling LLM.

Authentication uses the **shared Bearer contract**: every request carries
``Authorization: Bearer <google_id_token>``. The token is supplied per request
by an async ``token_provider`` (see :class:`brain_mcp.auth.TokenProvider`), which
transparently refreshes expired tokens. When no credentials are cached the
provider raises :class:`brain_mcp.auth.NotAuthenticatedError`, which is mapped to
:class:`BrainAuthError` with login guidance.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from brain_mcp import __version__
from brain_mcp.auth import NotAuthenticatedError

TokenProvider = Callable[[], Awaitable[str]]


class BrainAPIError(RuntimeError):
    """Base class for all Brain API failures surfaced to the caller."""


class BrainAuthError(BrainAPIError):
    """Authentication failed: missing/expired login or a rejected token (401/403)."""


class BrainUnreachableError(BrainAPIError):
    """The Web API could not be reached (connection/timeout)."""


class BrainResponseError(BrainAPIError):
    """The Web API returned an unexpected (non-2xx) response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class BrainClient:
    """Thin async client over the isitme Web API.

    All requests carry ``Authorization: Bearer <google_id_token>``, with the
    token fetched from ``token_provider`` (an async callable returning the
    current id_token) on each request so refreshes are picked up automatically.
    The instance owns a single :class:`httpx.AsyncClient`; call :meth:`aclose`
    (or use it as an async context manager) to release the connection pool. If
    the provider exposes ``aclose``, it is closed too.
    """

    def __init__(
        self,
        base_url: str,
        token_provider: TokenProvider,
        *,
        timeout: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token_provider = token_provider
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={
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
        provider_close = getattr(self._token_provider, "__self__", None)
        if provider_close is not None and hasattr(provider_close, "aclose"):
            await provider_close.aclose()

    async def _auth_header(self) -> dict[str, str]:
        try:
            token = await self._token_provider()
        except NotAuthenticatedError as exc:
            raise BrainAuthError(str(exc)) from exc
        return {"Authorization": f"Bearer {token}"}

    # --- low-level request helper ------------------------------------------
    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers = await self._auth_header()
        try:
            resp = await self._client.request(
                method, path, json=json, params=params, headers=headers
            )
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
                f"The brain rejected your Google token (HTTP {resp.status_code}). "
                "Your login may have expired — re-run: python -m brain_mcp login"
            )
        if resp.status_code >= 400:
            raise BrainResponseError(
                f"Brain API error on {method} {path}: HTTP {resp.status_code} "
                f"{_safe_detail(resp)}",
                status_code=resp.status_code,
            )
        return _safe_json(resp)

    # --- endpoints ----------------------------------------------------------
    async def whoami(self) -> dict[str, Any]:
        """Resolve who the current token authenticates as via ``GET /auth/me``.

        Raises :class:`BrainAuthError` when the Web API does not recognize the
        token (so startup validation surfaces a clear, actionable message).
        """
        result = await self._request("GET", "/auth/me")
        if isinstance(result, dict) and not result.get("authenticated", False):
            raise BrainAuthError(
                "The Web API did not accept your Google token. "
                "Re-run: python -m brain_mcp login"
            )
        return result if isinstance(result, dict) else {"authenticated": True, "raw": result}

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
