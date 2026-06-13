"""Unit tests for :class:`web_api.google_auth.GoogleTokenVerifier`.

Google's network endpoints are stubbed:

* ``id_token`` verification (``google.oauth2.id_token.verify_oauth2_token``) is
  monkeypatched so we don't fetch real signing certs.
* the ``tokeninfo`` / ``userinfo`` HTTP calls run through an injected
  ``httpx.MockTransport`` (no network, no extra test deps).
"""

from __future__ import annotations

import httpx
import pytest

from web_api import google_auth
from web_api.google_auth import GoogleTokenVerifier

CLIENT_ID = "test-client.apps.googleusercontent.com"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_id_token_verified_offline(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_verify(token, request, audience, clock_skew_in_seconds=0):  # noqa: ARG001
        calls["n"] += 1
        assert audience == CLIENT_ID
        return {
            "iss": "https://accounts.google.com",
            "sub": "sub-1",
            "email": "a@example.com",
            "name": "A",
            "picture": "http://pic",
            "exp": 10_000_000_000,
        }

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", fake_verify)

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - unused
        raise AssertionError("id_token path must not hit the network")

    verifier = GoogleTokenVerifier(CLIENT_ID, http_client=_client(handler))
    identity = await verifier.verify("a.b.c")
    assert identity is not None
    assert identity.sub == "sub-1"
    assert identity.email == "a@example.com"

    # Second call for the same token is served from cache (no re-verification).
    again = await verifier.verify("a.b.c")
    assert again is identity
    assert calls["n"] == 1
    await verifier.aclose()


async def test_id_token_wrong_audience_rejected(monkeypatch) -> None:
    def fake_verify(token, request, audience, clock_skew_in_seconds=0):  # noqa: ARG001
        raise ValueError("Wrong recipient, payload audience != client_id")

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", fake_verify)

    # tokeninfo fallback also rejects it.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_token"})

    verifier = GoogleTokenVerifier(CLIENT_ID, http_client=_client(handler))
    assert await verifier.verify("a.b.c") is None
    await verifier.aclose()


async def test_access_token_verified_via_tokeninfo_and_userinfo(monkeypatch) -> None:
    # Force the id_token path to fail so we exercise the access_token fallback.
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("not a jwt")),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tokeninfo"):
            assert request.url.params.get("access_token") == "opaque-token"
            return httpx.Response(
                200,
                json={
                    "aud": CLIENT_ID,
                    "sub": "sub-2",
                    "email": "b@example.com",
                    "exp": "10000000000",
                },
            )
        # userinfo enrichment
        return httpx.Response(200, json={"name": "B", "picture": "http://pic2"})

    verifier = GoogleTokenVerifier(CLIENT_ID, http_client=_client(handler))
    identity = await verifier.verify("opaque-token")
    assert identity is not None
    assert identity.sub == "sub-2"
    assert identity.email == "b@example.com"
    assert identity.name == "B"
    await verifier.aclose()


async def test_access_token_wrong_audience_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("not a jwt")),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        # Token minted for a DIFFERENT client -> confused-deputy guard rejects it.
        return httpx.Response(200, json={"aud": "someone-else", "sub": "x", "exp": "10000000000"})

    verifier = GoogleTokenVerifier(CLIENT_ID, http_client=_client(handler))
    assert await verifier.verify("opaque-token") is None
    await verifier.aclose()


async def test_empty_token_is_none() -> None:
    verifier = GoogleTokenVerifier(CLIENT_ID, http_client=_client(lambda r: httpx.Response(400)))
    assert await verifier.verify("") is None
    assert await verifier.verify("   ") is None
    await verifier.aclose()


@pytest.mark.parametrize("expired_at", [0.0])
async def test_expired_cache_entry_revalidates(monkeypatch, expired_at) -> None:
    clock = {"t": 1000.0}

    def fake_verify(token, request, audience, clock_skew_in_seconds=0):  # noqa: ARG001
        return {"iss": "accounts.google.com", "sub": "s", "exp": clock["t"] + 5}

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", fake_verify)
    verifier = GoogleTokenVerifier(
        CLIENT_ID, http_client=_client(lambda r: httpx.Response(400)), now=lambda: clock["t"]
    )
    first = await verifier.verify("a.b.c")
    assert first is not None
    # Advance the clock past the cached expiry; a fresh verification happens.
    clock["t"] += 100
    second = await verifier.verify("a.b.c")
    assert second is not None and second is not first
    await verifier.aclose()
