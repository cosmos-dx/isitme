"""Authentication tests (run against the default SQLite store).

Covers the shared auth contract:

* the **Google Bearer** path (the documented contract for MCP + the extension):
  a verified token is accepted and resolves-or-creates the user; an unverified
  token is rejected. Google verification is mocked so the tests never touch the
  network.
* the **legacy X-API-Key** path: a valid key is accepted, an
  invalid/missing/revoked one is rejected, and the data endpoints accept the key
  (reaching the brain proxy rather than 401).

Also unit-tests the MongoWebStore key path when `mongomock-motor` is available.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from web_api.app import create_app
from web_api.config import Settings
from web_api.google_auth import VerifiedIdentity
from web_api.security import generate_api_key
from web_api.store import SqliteWebStore


class _FakeVerifier:
    """Stand-in for GoogleTokenVerifier: accepts pre-seeded tokens only."""

    def __init__(self, tokens: dict[str, VerifiedIdentity]) -> None:
        self._tokens = tokens
        self.calls: list[str] = []

    async def verify(self, token: str) -> VerifiedIdentity | None:
        self.calls.append(token)
        return self._tokens.get(token)

    async def aclose(self) -> None:  # pragma: no cover - parity with real verifier
        return None


def _settings(tmp_path) -> Settings:
    s = Settings()
    s.mongo_uri = None  # force SQLite regardless of the environment
    s.db_url = f"sqlite+aiosqlite:///{tmp_path / 'web.db'}"
    return s


def _seed_keys(db_url: str) -> tuple[str, str]:
    """Create a user with one active key and one revoked key; return both plaintexts."""

    async def _run() -> tuple[str, str]:
        store = SqliteWebStore(db_url)
        await store.init()
        try:
            uid = await store.upsert_user("sub-test", "t@example.com", "Tester", None)
            active = generate_api_key()
            await store.create_api_key(uid, "active", active)
            revoked = generate_api_key()
            meta = await store.create_api_key(uid, "revoked", revoked)
            await store.revoke_api_key(uid, meta["id"])
            return active.plaintext, revoked.plaintext
        finally:
            await store.close()

    return asyncio.run(_run())


def test_api_key_validate_accepts_valid_rejects_invalid(tmp_path) -> None:
    settings = _settings(tmp_path)
    active_key, revoked_key = _seed_keys(settings.db_url)

    with TestClient(create_app(settings)) as client:
        ok = client.get("/api/keys/validate", headers={"X-API-Key": active_key})
        assert ok.status_code == 200
        body = ok.json()
        assert body["valid"] is True
        assert body["user"]["email"] == "t@example.com"

        # Missing header, garbage key and revoked key are all rejected.
        assert client.get("/api/keys/validate").status_code == 401
        assert (
            client.get("/api/keys/validate", headers={"X-API-Key": "isme_bogus"}).status_code
            == 401
        )
        assert (
            client.get("/api/keys/validate", headers={"X-API-Key": revoked_key}).status_code
            == 401
        )


def test_data_endpoint_accepts_api_key(tmp_path) -> None:
    settings = _settings(tmp_path)
    active_key, _ = _seed_keys(settings.db_url)

    with TestClient(create_app(settings)) as client:
        # No auth -> 401.
        assert client.get("/api/stats").status_code == 401
        # Valid key passes auth; brain is offline in tests so it surfaces 502,
        # which still proves the key was accepted (not 401).
        with_key = client.get("/api/stats", headers={"X-API-Key": active_key})
        assert with_key.status_code != 401


def test_session_only_routes_reject_api_key(tmp_path) -> None:
    settings = _settings(tmp_path)
    active_key, _ = _seed_keys(settings.db_url)

    with TestClient(create_app(settings)) as client:
        # Key management stays browser/session only.
        assert (
            client.get("/api/keys", headers={"X-API-Key": active_key}).status_code == 401
        )


def test_bearer_token_accepted_and_resolves_user(tmp_path) -> None:
    settings = _settings(tmp_path)
    identity = VerifiedIdentity(
        sub="google-sub-123",
        email="bearer@example.com",
        name="Bearer User",
        picture=None,
        expires_at=9_999_999_999.0,
    )
    with TestClient(create_app(settings)) as client:
        client.app.state.google_verifier = _FakeVerifier({"good-token": identity})

        # /auth/me resolves the verified Google identity from the Bearer token.
        me = client.get("/auth/me", headers={"Authorization": "Bearer good-token"})
        assert me.status_code == 200
        body = me.json()
        assert body["authenticated"] is True
        assert body["user"]["email"] == "bearer@example.com"

        # A data endpoint accepts the Bearer token (brain offline -> 502, not 401).
        stats = client.get("/api/stats", headers={"Authorization": "Bearer good-token"})
        assert stats.status_code != 401


def test_bearer_token_invalid_rejected(tmp_path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.app.state.google_verifier = _FakeVerifier({})

        # Unverified token -> 401 on guarded routes.
        assert (
            client.get("/api/stats", headers={"Authorization": "Bearer nope"}).status_code
            == 401
        )
        # Malformed Authorization header is ignored (no Bearer prefix).
        assert client.get("/api/stats", headers={"Authorization": "good-token"}).status_code == 401
        # /auth/me reports unauthenticated rather than erroring.
        me = client.get("/auth/me", headers={"Authorization": "Bearer nope"})
        assert me.status_code == 200 and me.json()["authenticated"] is False


def test_oauth_config_exposes_client_id_not_secret(tmp_path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        resp = client.get("/auth/oauth-config")
        assert resp.status_code == 200
        body = resp.json()
        # When OAUTH_CLIENT_JSON is present the client_id is exposed publicly.
        if body["configured"]:
            assert body["client_id"]
            assert "openid" in body["scopes"]
            # The secret must never be serialized anywhere in the response.
            assert "secret" not in resp.text.lower()


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("mongomock_motor") is None,
    reason="mongomock-motor not installed",
)
def test_mongo_web_store_key_lifecycle() -> None:
    from mongomock_motor import AsyncMongoMockClient

    from web_api.store import MongoWebStore

    async def _run() -> None:
        store = MongoWebStore("mongodb://unused", "isitme_test", client=AsyncMongoMockClient())
        await store.init()
        uid = await store.upsert_user("sub-m", "m@example.com", "M", None)
        gen = generate_api_key()
        meta = await store.create_api_key(uid, "k", gen)

        user = await store.authenticate_key(gen.plaintext)
        assert user is not None and user["id"] == uid
        assert await store.authenticate_key("isme_bad") is None

        assert await store.revoke_api_key(uid, meta["id"]) is True
        assert await store.authenticate_key(gen.plaintext) is None
        await store.close()

    asyncio.run(_run())
