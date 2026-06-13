"""Smoke tests: the app boots, public routes respond, protected routes 401.

These run without a live Core Brain — ``/healthz`` reports the brain as
unreachable rather than failing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from web_api.app import create_app


def test_app_boots_and_health() -> None:
    with TestClient(create_app()) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_unauthenticated_me_and_guarded_routes() -> None:
    with TestClient(create_app()) as client:
        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["authenticated"] is False

        # Protected routes require a session.
        assert client.get("/api/keys").status_code == 401
        assert client.get("/api/graph").status_code == 401
        assert client.get("/api/mcp-config").status_code == 401
