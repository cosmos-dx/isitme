"""Server-side verification of Google OAuth tokens (the shared Bearer contract).

Non-browser clients (the MCP server and the browser extension) authenticate by
sending ``Authorization: Bearer <google_oauth_token>``. The token is one of:

* an **OIDC id_token** (preferred) — a signed JWT. We verify the signature,
  issuer, expiry and that ``aud`` matches *our* OAuth ``client_id`` using
  ``google-auth`` (:func:`google.oauth2.id_token.verify_oauth2_token`).
* a Google **access_token** — an opaque token. We verify it against Google's
  ``tokeninfo`` endpoint and confirm it was issued for our ``client_id``
  (``aud``/``azp``), then enrich the profile from ``userinfo``.

We **never** trust unverified claims: a token is only accepted after Google (or
Google's published signing keys) vouches for it AND its audience is ours.
Successful verifications are cached by token until shortly before they expire so
the hot path doesn't hammer Google on every request.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Tolerate small clock differences when validating ``exp``/``iat``.
_CLOCK_SKEW_SECONDS = 10
# Never cache a verification result for longer than this, even if the token's
# own expiry is far away — keeps revocation/expiry reasonably fresh.
_MAX_CACHE_TTL_SECONDS = 3600.0
# Treat a token as expired this many seconds early (defensive margin).
_EXPIRY_MARGIN_SECONDS = 30.0
_VALID_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


@dataclass(frozen=True)
class VerifiedIdentity:
    """A Google identity proven by a verified token."""

    sub: str
    email: str | None
    name: str | None
    picture: str | None
    # Epoch seconds after which this verification must not be trusted.
    expires_at: float


class GoogleTokenVerifier:
    """Verifies Google Bearer tokens against Google and caches the result.

    ``http_client`` and ``now`` are injectable for tests. The verifier owns its
    :class:`httpx.AsyncClient` unless one is supplied; call :meth:`aclose` to
    release it.
    """

    def __init__(
        self,
        client_id: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        now: object = time.time,
    ) -> None:
        self._client_id = client_id
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None
        self._now = now  # type: ignore[assignment]
        self._cache: dict[str, VerifiedIdentity] = {}
        self._lock = asyncio.Lock()

    @property
    def client_id(self) -> str:
        return self._client_id

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _clock(self) -> float:
        return float(self._now())  # type: ignore[operator]

    def _cap_expiry(self, token_exp: float) -> float:
        now = self._clock()
        ceiling = now + _MAX_CACHE_TTL_SECONDS
        usable = (token_exp - _EXPIRY_MARGIN_SECONDS) if token_exp else ceiling
        return max(now, min(usable, ceiling))

    async def verify(self, token: str) -> VerifiedIdentity | None:
        """Resolve a verified identity for ``token`` or ``None`` if invalid."""
        token = (token or "").strip()
        if not token:
            return None
        now = self._clock()
        async with self._lock:
            cached = self._cache.get(token)
            if cached is not None:
                if cached.expires_at > now:
                    return cached
                self._cache.pop(token, None)

        identity = await self._verify_id_token(token)
        if identity is None:
            identity = await self._verify_access_token(token)
        if identity is not None:
            async with self._lock:
                self._cache[token] = identity
        return identity

    async def _verify_id_token(self, token: str) -> VerifiedIdentity | None:
        """Verify an OIDC id_token (JWT) offline against Google's signing keys."""
        # Cheap pre-filter: id_tokens are JWTs (header.payload.signature).
        if token.count(".") != 2:
            return None
        try:
            claims = await asyncio.to_thread(
                google_id_token.verify_oauth2_token,
                token,
                google_requests.Request(),
                self._client_id,
                clock_skew_in_seconds=_CLOCK_SKEW_SECONDS,
            )
        except (ValueError, GoogleAuthError):
            # Bad signature, wrong audience, expired, or simply not an id_token.
            return None
        if claims.get("iss") not in _VALID_ISSUERS:
            return None
        sub = claims.get("sub")
        if not sub:
            return None
        return VerifiedIdentity(
            sub=str(sub),
            email=_str_or_none(claims.get("email")),
            name=_str_or_none(claims.get("name")),
            picture=_str_or_none(claims.get("picture")),
            expires_at=self._cap_expiry(float(claims.get("exp", 0) or 0)),
        )

    async def _verify_access_token(self, token: str) -> VerifiedIdentity | None:
        """Verify an opaque access_token via tokeninfo; enrich via userinfo."""
        try:
            resp = await self._client.get(TOKENINFO_URL, params={"access_token": token})
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            info = resp.json()
        except ValueError:
            return None
        # The token MUST have been minted for our client (confused-deputy guard).
        audience = info.get("aud") or info.get("azp")
        if audience != self._client_id:
            return None
        sub = info.get("sub")
        if not sub:
            return None
        expires_at = self._access_token_expiry(info)
        name = None
        picture = None
        profile = await self._fetch_userinfo(token)
        if profile is not None:
            name = _str_or_none(profile.get("name"))
            picture = _str_or_none(profile.get("picture"))
        return VerifiedIdentity(
            sub=str(sub),
            email=_str_or_none(info.get("email")),
            name=name,
            picture=picture,
            expires_at=expires_at,
        )

    def _access_token_expiry(self, info: dict[str, object]) -> float:
        exp = info.get("exp")
        if exp is not None:
            try:
                return self._cap_expiry(float(exp))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        expires_in = info.get("expires_in")
        if expires_in is not None:
            try:
                return self._cap_expiry(self._clock() + float(expires_in))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                pass
        return self._cap_expiry(0)

    async def _fetch_userinfo(self, token: str) -> dict[str, object] | None:
        try:
            resp = await self._client.get(
                USERINFO_URL, headers={"Authorization": f"Bearer {token}"}
            )
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        try:
            data = resp.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
