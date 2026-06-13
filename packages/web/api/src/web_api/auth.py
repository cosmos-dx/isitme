"""Unified authentication for the Web API.

A request is authenticated if it carries ANY of:

* a valid browser **session cookie** (set after Google OAuth), OR
* a header ``Authorization: Bearer <google_oauth_token>`` — the **documented
  path for the MCP server and the browser extension**. The token is a Google
  OAuth token (an OIDC ``id_token`` or an ``access_token``); it is verified
  server-side against Google (see :mod:`web_api.google_auth`) and the verified
  ``email``/``sub`` resolves-or-creates the user, OR
* a header ``X-API-Key: <plaintext>`` whose SHA-256 hash matches a stored,
  non-revoked key (**legacy/optional** — kept working but no longer the
  recommended path for new clients).

We never trust unverified token claims: a Bearer token is only honored after
Google vouches for it and its audience matches our OAuth ``client_id``.

These are plain ``Request`` helpers (not ``Depends`` factories) so they can be
reused by any route and resolve ``app.state.store`` / ``app.state.google_verifier``
at call time.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

API_KEY_HEADER = "X-API-Key"
BEARER_PREFIX = "bearer "


def _store(request: Request) -> Any:
    return request.app.state.store


def _bearer_token(request: Request) -> str | None:
    """Extract the raw token from an ``Authorization: Bearer <token>`` header."""
    header = request.headers.get("Authorization")
    if not header:
        return None
    if not header.lower().startswith(BEARER_PREFIX):
        return None
    token = header[len(BEARER_PREFIX) :].strip()
    return token or None


async def current_user(request: Request) -> dict[str, Any] | None:
    """The session-cookie user, if any (no token / API-key fallback)."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return await _store(request).get_user(user_id)


async def user_from_bearer(request: Request) -> dict[str, Any] | None:
    """The user resolved from a verified Google ``Authorization: Bearer`` token.

    The token is verified against Google; the proven ``sub``/``email`` is then
    resolved-or-created in the store (updating ``last_login``).
    """
    token = _bearer_token(request)
    if not token:
        return None
    verifier = getattr(request.app.state, "google_verifier", None)
    if verifier is None:
        return None
    identity = await verifier.verify(token)
    if identity is None:
        return None
    store = _store(request)
    user_id = await store.upsert_user(
        google_sub=identity.sub,
        email=identity.email,
        name=identity.name,
        picture=identity.picture,
    )
    return await store.get_user(user_id)


async def user_from_api_key(request: Request) -> dict[str, Any] | None:
    """The user resolved from a presented ``X-API-Key`` header, if valid (legacy)."""
    key = request.headers.get(API_KEY_HEADER)
    if not key:
        return None
    return await _store(request).authenticate_key(key)


async def authenticate(request: Request) -> dict[str, Any] | None:
    """Resolve the user from a session cookie, a Google Bearer token, or an API key."""
    user = await current_user(request)
    if user:
        return user
    user = await user_from_bearer(request)
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
    """Session / Google-Bearer / API-key guard for endpoints shared with MCP + the extension."""
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
