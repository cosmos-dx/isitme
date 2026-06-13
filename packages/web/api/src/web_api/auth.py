"""Unified authentication for the Web API.

A request is authenticated if it carries EITHER:

* a valid browser **session cookie** (set after Google OAuth), OR
* a header ``X-API-Key: <plaintext>`` whose SHA-256 hash matches a stored,
  non-revoked key.

Plaintext keys are never stored or logged: :meth:`WebStore.authenticate_key`
hashes the presented key locally, looks up the hash, resolves the owning user
and updates ``last_used``.

These are plain ``Request`` helpers (not ``Depends`` factories) so they can be
reused by any route and resolve ``app.state.store`` at call time.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

API_KEY_HEADER = "X-API-Key"


def _store(request: Request) -> Any:
    return request.app.state.store


async def current_user(request: Request) -> dict[str, Any] | None:
    """The session-cookie user, if any (no API-key fallback)."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await _store(request).get_user(user_id)


async def user_from_api_key(request: Request) -> dict[str, Any] | None:
    """The user resolved from a presented ``X-API-Key`` header, if valid."""
    key = request.headers.get(API_KEY_HEADER)
    if not key:
        return None
    return await _store(request).authenticate_key(key)


async def authenticate(request: Request) -> dict[str, Any] | None:
    """Resolve the user from a session cookie OR a valid API key."""
    user = await current_user(request)
    if user:
        return user
    return await user_from_api_key(request)


async def require_user(request: Request) -> dict[str, Any]:
    """Session-only guard (used for browser-driven API-key management)."""
    user = await current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_auth(request: Request) -> dict[str, Any]:
    """Session-or-API-key guard for endpoints shared with MCP / the extension."""
    user = await authenticate(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


async def require_api_key(request: Request) -> dict[str, Any]:
    """Require a valid ``X-API-Key`` specifically (e.g. key validation)."""
    if not request.headers.get(API_KEY_HEADER):
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    user = await user_from_api_key(request)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return user
