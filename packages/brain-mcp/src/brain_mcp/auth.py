"""Google OAuth for the Brain MCP server: login, credential storage, refresh.

The MCP server authenticates to the Web API with the **shared Bearer contract**:
every request carries ``Authorization: Bearer <google_id_token>``. There is no
API key.

This module owns three things:

* :func:`login` — an interactive, one-time ``python -m brain_mcp login`` flow. It
  runs Google's Authorization Code + PKCE flow over a **loopback redirect**
  (``http://127.0.0.1:<port>/callback``), opens the browser, captures the code,
  exchanges it for tokens, and caches them under ``~/.isitme/credentials.json``
  (chmod ``600``).
* :class:`Credentials` + load/save helpers — the on-disk token cache (access +
  refresh + id_token + expiry + the client_id/secret needed to refresh).
* :class:`TokenProvider` — returns a currently-valid ``id_token`` for each API
  call, **transparently refreshing** via Google's token endpoint when expired.
  When there are no cached credentials it raises :class:`NotAuthenticatedError`
  with an actionable "run ``python -m brain_mcp login``" message.

The OAuth client (``client_id`` + ``client_secret``) is read from the project's
root ``.env`` (``OAUTH_CLIENT_JSON``); the non-secret ``client_id`` can also be
discovered from the Web API's ``GET /auth/oauth-config``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import httpx

DEFAULT_CREDENTIALS_PATH = Path.home() / ".isitme" / "credentials.json"
DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ("openid", "email", "profile")
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Refresh a little before the token actually expires to avoid edge races.
_EXPIRY_MARGIN_SECONDS = 60.0

LOGIN_HINT = (
    "Not authenticated to the isitme brain. Run a one-time interactive login:\n"
    "    python -m brain_mcp login\n"
    "This opens Google sign-in and caches your tokens under "
    f"{DEFAULT_CREDENTIALS_PATH}."
)


class NotAuthenticatedError(RuntimeError):
    """No usable cached credentials — the user must run ``python -m brain_mcp login``."""


class LoginError(RuntimeError):
    """The interactive login flow could not complete."""


@dataclass
class OAuthClientInfo:
    """The (confidential web) OAuth client used for the loopback CLI flow."""

    client_id: str
    client_secret: str
    auth_uri: str = DEFAULT_AUTH_URI
    token_uri: str = DEFAULT_TOKEN_URI


@dataclass
class Credentials:
    """Cached Google tokens + the material needed to refresh them."""

    client_id: str
    client_secret: str
    token_uri: str
    id_token: str | None
    access_token: str | None
    refresh_token: str | None
    expiry: float  # epoch seconds when the id/access token expires
    scope: str = ""
    email: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token_uri": self.token_uri,
            "id_token": self.id_token,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expiry": self.expiry,
            "scope": self.scope,
            "email": self.email,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Credentials:
        return cls(
            client_id=str(data.get("client_id", "")),
            client_secret=str(data.get("client_secret", "")),
            token_uri=str(data.get("token_uri", DEFAULT_TOKEN_URI)),
            id_token=data.get("id_token"),
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            expiry=float(data.get("expiry", 0) or 0),
            scope=str(data.get("scope", "")),
            email=data.get("email"),
        )


def load_credentials(path: Path = DEFAULT_CREDENTIALS_PATH) -> Credentials | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return Credentials.from_json(data)


def save_credentials(creds: Credentials, path: Path = DEFAULT_CREDENTIALS_PATH) -> None:
    """Persist credentials with owner-only permissions (chmod 600 / dir 700)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:  # pragma: no cover - best effort on some filesystems
        pass
    path.write_text(json.dumps(creds.to_json(), indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:  # pragma: no cover - best effort on some filesystems
        pass


class TokenProvider:
    """Supplies a valid Google ``id_token`` per request, refreshing as needed.

    ``http_client`` and ``now`` are injectable for tests. Thread-safe across
    concurrent tool calls via an :class:`asyncio.Lock`.
    """

    def __init__(
        self,
        path: Path = DEFAULT_CREDENTIALS_PATH,
        *,
        http_client: httpx.AsyncClient | None = None,
        now: Any = time.time,
    ) -> None:
        self._path = path
        self._client = http_client
        self._owns_client = http_client is None
        self._now = now
        self._creds: Credentials | None = None
        self._lock = asyncio.Lock()

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def id_token(self) -> str:
        """Return a currently-valid id_token, refreshing if it has expired.

        Raises :class:`NotAuthenticatedError` (with login guidance) when there
        are no cached credentials or a refresh is impossible.
        """
        async with self._lock:
            creds = self._creds or load_credentials(self._path)
            if creds is None:
                raise NotAuthenticatedError(LOGIN_HINT)
            self._creds = creds
            now = float(self._now())
            if creds.id_token and creds.expiry - _EXPIRY_MARGIN_SECONDS > now:
                return creds.id_token
            refreshed = await self._refresh(creds)
            self._creds = refreshed
            save_credentials(refreshed, self._path)
            if not refreshed.id_token:
                raise NotAuthenticatedError(
                    "Google did not return an id_token on refresh. "
                    "Re-run: python -m brain_mcp login"
                )
            return refreshed.id_token

    async def _refresh(self, creds: Credentials) -> Credentials:
        if not creds.refresh_token:
            raise NotAuthenticatedError(
                "Cached credentials have expired and there is no refresh token. "
                "Re-run: python -m brain_mcp login"
            )
        try:
            resp = await self._http().post(
                creds.token_uri,
                data={
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "refresh_token": creds.refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError as exc:
            raise NotAuthenticatedError(
                f"Could not reach Google to refresh the token ({exc.__class__.__name__}). "
                "Check your connection and retry."
            ) from exc
        if resp.status_code != 200:
            raise NotAuthenticatedError(
                f"Token refresh was rejected by Google (HTTP {resp.status_code}). "
                "Re-run: python -m brain_mcp login"
            )
        data = resp.json()
        return replace(
            creds,
            access_token=data.get("access_token", creds.access_token),
            id_token=data.get("id_token", creds.id_token),
            expiry=float(self._now()) + float(data.get("expires_in", 3600) or 3600),
            scope=data.get("scope", creds.scope),
        )


# --- OAuth client discovery ------------------------------------------------


def resolve_oauth_client(
    *,
    api_base: str | None = None,
    env: dict[str, str] | None = None,
) -> OAuthClientInfo:
    """Resolve the OAuth client (id + secret) for the loopback login flow.

    Primary source is ``OAUTH_CLIENT_JSON`` in the environment / repo-root
    ``.env`` (loaded by the config layer) — it carries the confidential
    ``client_secret`` required to exchange the auth code. As a convenience the
    non-secret ``client_id`` can be discovered from the Web API's
    ``/auth/oauth-config`` but the secret must still come from the environment.
    """
    env = env if env is not None else dict(os.environ)
    raw = env.get("OAUTH_CLIENT_JSON")
    if raw:
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise LoginError(f"OAUTH_CLIENT_JSON is not valid JSON: {exc}") from exc
        web = data.get("web") or data.get("installed") or data
        client_id = web.get("client_id")
        client_secret = web.get("client_secret")
        if client_id and client_secret:
            return OAuthClientInfo(
                client_id=client_id,
                client_secret=client_secret,
                auth_uri=web.get("auth_uri", DEFAULT_AUTH_URI),
                token_uri=web.get("token_uri", DEFAULT_TOKEN_URI),
            )
    raise LoginError(
        "Could not find a Google OAuth client with a client_secret.\n"
        "Set OAUTH_CLIENT_JSON in the environment or the repo-root .env (the same\n"
        "value the Web API uses). The CLI login needs the client_secret to exchange\n"
        "the authorization code; the Web API only exposes the non-secret client_id."
    )


# --- interactive login -----------------------------------------------------


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        self.server.auth_result = params  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = "error" not in params and "code" in params
        msg = "Sign-in complete" if ok else "Sign-in failed"
        self.wfile.write(
            f"<!doctype html><html><body style='font-family:sans-serif'>"
            f"<h2>isitme — {msg}.</h2><p>You can close this tab and return to "
            f"your terminal.</p></body></html>".encode()
        )

    def log_message(self, *args: Any) -> None:  # silence the default stderr logging
        return


def _capture_redirect(port: int, state: str, timeout: float) -> dict[str, str]:
    try:
        server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    except OSError as exc:
        raise LoginError(
            f"Could not bind the loopback callback server on 127.0.0.1:{port} ({exc}). "
            "Choose a free port via BRAIN_OAUTH_REDIRECT_PORT and ensure the matching "
            "redirect URI is registered in Google Cloud."
        ) from exc
    server.auth_result = None  # type: ignore[attr-defined]
    server.timeout = 1.0
    deadline = time.time() + timeout
    try:
        while server.auth_result is None and time.time() < deadline:  # type: ignore[attr-defined]
            server.handle_request()
    finally:
        server.server_close()
    result: dict[str, str] | None = server.auth_result  # type: ignore[attr-defined]
    if not result:
        raise LoginError("Timed out waiting for the Google OAuth redirect.")
    if result.get("state") != state:
        raise LoginError("OAuth state mismatch — aborting for safety.")
    if "error" in result:
        raise LoginError(f"Google returned an error: {result['error']}")
    if "code" not in result:
        raise LoginError("No authorization code was returned by Google.")
    return result


def login(
    client_info: OAuthClientInfo,
    *,
    path: Path = DEFAULT_CREDENTIALS_PATH,
    port: int = 8765,
    open_browser: bool = True,
    timeout: float = 300.0,
    print_fn: Any = print,
) -> Credentials:
    """Run the interactive loopback OAuth flow and cache the resulting tokens."""
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    state = secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    auth_url = client_info.auth_uri + "?" + urllib.parse.urlencode(
        {
            "client_id": client_info.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(SCOPES),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
        }
    )

    print_fn(f"\nUsing loopback redirect: {redirect_uri}")
    print_fn(
        "If Google shows a redirect_uri_mismatch, add that exact URI to the OAuth "
        "client's Authorized redirect URIs in Google Cloud Console.\n"
    )
    print_fn("Opening your browser to sign in with Google…")
    print_fn(f"If it doesn't open, visit this URL manually:\n{auth_url}\n")
    if open_browser:
        try:
            webbrowser.open(auth_url)
        except webbrowser.Error:  # pragma: no cover - headless environments
            pass

    result = _capture_redirect(port, state, timeout)
    code = result["code"]

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                client_info.token_uri,
                data={
                    "client_id": client_info.client_id,
                    "client_secret": client_info.client_secret,
                    "code": code,
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
    except httpx.HTTPError as exc:
        raise LoginError(f"Could not reach Google's token endpoint: {exc}") from exc
    if resp.status_code != 200:
        raise LoginError(
            f"Token exchange failed (HTTP {resp.status_code}): {resp.text[:300]}"
        )
    token = resp.json()
    creds = Credentials(
        client_id=client_info.client_id,
        client_secret=client_info.client_secret,
        token_uri=client_info.token_uri,
        id_token=token.get("id_token"),
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        expiry=time.time() + float(token.get("expires_in", 3600) or 3600),
        scope=token.get("scope", ""),
    )
    if not creds.id_token:
        raise LoginError(
            "Google did not return an id_token. Ensure the 'openid' scope is enabled."
        )
    creds.email = _email_from_token(token)
    save_credentials(creds, path)
    return creds


def _email_from_token(token: dict[str, Any]) -> str | None:
    """Best-effort: read the email claim from the id_token payload (unverified).

    Used only for a friendly "logged in as <email>" message; the Web API still
    verifies the token on every call.
    """
    raw = token.get("id_token")
    if not isinstance(raw, str) or raw.count(".") != 2:
        return None
    try:
        payload_b64 = raw.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError):
        return None
    email = payload.get("email")
    return email if isinstance(email, str) else None
