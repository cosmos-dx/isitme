"""Tests for the OAuth token layer (credentials, refresh, client discovery).

The interactive browser ``login()`` flow isn't exercised here (it needs a real
browser + Google); instead we cover the parts the MCP server relies on at
runtime: credential persistence, ``TokenProvider`` (valid / expired / missing),
and OAuth client resolution from ``OAUTH_CLIENT_JSON``.
"""

from __future__ import annotations

import json
import stat

import httpx
import pytest
import respx

from brain_mcp.auth import (
    Credentials,
    LoginError,
    NotAuthenticatedError,
    TokenProvider,
    load_credentials,
    resolve_oauth_client,
    save_credentials,
)

TOKEN_URI = "https://oauth2.googleapis.com/token"


def _creds(**overrides) -> Credentials:
    base = dict(
        client_id="cid",
        client_secret="secret",
        token_uri=TOKEN_URI,
        id_token="id-token",
        access_token="access-token",
        refresh_token="refresh-token",
        expiry=10_000.0,
        scope="openid email profile",
        email="me@example.com",
    )
    base.update(overrides)
    return Credentials(**base)


def test_credentials_roundtrip_and_permissions(tmp_path) -> None:
    path = tmp_path / "nested" / "credentials.json"
    creds = _creds()
    save_credentials(creds, path)

    assert path.exists()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600  # owner read/write only

    loaded = load_credentials(path)
    assert loaded is not None
    assert loaded.id_token == "id-token"
    assert loaded.email == "me@example.com"


def test_load_credentials_missing_returns_none(tmp_path) -> None:
    assert load_credentials(tmp_path / "absent.json") is None


async def test_token_provider_returns_valid_cached_id_token(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    save_credentials(_creds(expiry=10_000.0), path)
    provider = TokenProvider(path, now=lambda: 1_000.0)  # not expired
    assert await provider.id_token() == "id-token"
    await provider.aclose()


async def test_token_provider_missing_credentials_raises(tmp_path) -> None:
    provider = TokenProvider(tmp_path / "absent.json")
    with pytest.raises(NotAuthenticatedError) as excinfo:
        await provider.id_token()
    assert "login" in str(excinfo.value)
    await provider.aclose()


@respx.mock
async def test_token_provider_refreshes_expired_token(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    # expiry in the past relative to our fake clock -> must refresh.
    save_credentials(_creds(expiry=500.0, id_token="stale"), path)
    route = respx.post(TOKEN_URI).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "id_token": "new-id-token",
                "expires_in": 3600,
                "scope": "openid email profile",
            },
        )
    )
    provider = TokenProvider(
        path, http_client=httpx.AsyncClient(), now=lambda: 1_000.0
    )
    token = await provider.id_token()
    assert token == "new-id-token"
    assert route.called
    # Refresh sent grant_type=refresh_token with the stored refresh token.
    sent = dict(httpx.QueryParams(route.calls.last.request.content.decode()))
    assert sent["grant_type"] == "refresh_token"
    assert sent["refresh_token"] == "refresh-token"
    # The refreshed token is persisted back to disk.
    on_disk = json.loads(path.read_text())
    assert on_disk["id_token"] == "new-id-token"
    await provider.aclose()


@respx.mock
async def test_token_provider_refresh_rejected_raises(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    save_credentials(_creds(expiry=500.0), path)
    respx.post(TOKEN_URI).mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    provider = TokenProvider(path, http_client=httpx.AsyncClient(), now=lambda: 1_000.0)
    with pytest.raises(NotAuthenticatedError):
        await provider.id_token()
    await provider.aclose()


async def test_token_provider_expired_without_refresh_token_raises(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    save_credentials(_creds(expiry=500.0, refresh_token=None), path)
    provider = TokenProvider(path, now=lambda: 1_000.0)
    with pytest.raises(NotAuthenticatedError):
        await provider.id_token()
    await provider.aclose()


def test_resolve_oauth_client_from_env() -> None:
    raw = json.dumps(
        {
            "web": {
                "client_id": "the-client-id",
                "client_secret": "the-secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": TOKEN_URI,
            }
        }
    )
    info = resolve_oauth_client(env={"OAUTH_CLIENT_JSON": raw})
    assert info.client_id == "the-client-id"
    assert info.client_secret == "the-secret"
    assert info.token_uri == TOKEN_URI


def test_resolve_oauth_client_missing_raises() -> None:
    with pytest.raises(LoginError):
        resolve_oauth_client(env={})
