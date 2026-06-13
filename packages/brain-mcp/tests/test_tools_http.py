"""HTTP-layer tests: each tool hits the right endpoint with the X-API-Key header.

The Web API is mocked with ``respx``; we drive the tools through the real
FastMCP ``call_tool`` path so the server -> client -> httpx wiring is exercised
end to end (minus the network).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from brain_mcp.client import (
    BrainAuthError,
    BrainClient,
    BrainResponseError,
    BrainUnreachableError,
)
from brain_mcp.config import BrainMCPConfig
from brain_mcp.server import build_server

API_BASE = "http://brain.test:5050"
API_KEY = "isme_unit_test_key"


@pytest.fixture
async def server_and_client():
    cfg = BrainMCPConfig(api_key=API_KEY, api_base=API_BASE)
    client = BrainClient(API_BASE, API_KEY)
    server = build_server(cfg, client=client)
    try:
        yield server, client
    finally:
        await client.aclose()


def _assert_authed(route: respx.Route, method: str, path: str) -> httpx.Request:
    assert route.called, f"expected a call to {path}"
    request = route.calls.last.request
    assert request.method == method
    assert request.url.path == path
    assert request.headers.get("x-api-key") == API_KEY
    return request


@respx.mock
async def test_recall_context(server_and_client) -> None:
    server, _ = server_and_client
    route = respx.post(f"{API_BASE}/api/recall").mock(
        return_value=httpx.Response(200, json={"memories": [{"id": "m1"}]})
    )
    await server.call_tool("recall_context", {"query": "my python notes", "k": 3})
    request = _assert_authed(route, "POST", "/api/recall")
    import json

    assert json.loads(request.content) == {"query": "my python notes", "k": 3}


@respx.mock
async def test_search_memory(server_and_client) -> None:
    server, _ = server_and_client
    route = respx.post(f"{API_BASE}/api/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    await server.call_tool("search_memory", {"query": "rust vs go", "k": 5})
    import json

    request = _assert_authed(route, "POST", "/api/search")
    assert json.loads(request.content) == {"query": "rust vs go", "k": 5}


@respx.mock
async def test_get_user_profile(server_and_client) -> None:
    server, _ = server_and_client
    route = respx.get(f"{API_BASE}/api/profile").mock(
        return_value=httpx.Response(200, json={"summary": "curious builder"})
    )
    await server.call_tool("get_user_profile", {})
    _assert_authed(route, "GET", "/api/profile")


@respx.mock
async def test_ask_brain(server_and_client) -> None:
    server, _ = server_and_client
    route = respx.post(f"{API_BASE}/api/ask").mock(
        return_value=httpx.Response(200, json={"answer": "yes", "sources": []})
    )
    await server.call_tool("ask_brain", {"question": "what do I like?", "k": 4})
    import json

    request = _assert_authed(route, "POST", "/api/ask")
    assert json.loads(request.content) == {"question": "what do I like?", "k": 4}


@respx.mock
async def test_log_interaction(server_and_client) -> None:
    server, _ = server_and_client
    route = respx.post(f"{API_BASE}/api/log").mock(
        return_value=httpx.Response(200, json={"ok": True, "id": "e1"})
    )
    await server.call_tool(
        "log_interaction",
        {
            "type": "opinion",
            "content": "I prefer typed languages.",
            "data": {"confidence": 0.9},
        },
    )
    import json

    request = _assert_authed(route, "POST", "/api/log")
    body = json.loads(request.content)
    assert body["type"] == "opinion"
    assert body["content"] == "I prefer typed languages."
    assert body["source"] == "mcp"
    assert body["data"] == {"confidence": 0.9}


@respx.mock
async def test_log_interaction_rejects_bad_type(server_and_client) -> None:
    server, _ = server_and_client
    route = respx.post(f"{API_BASE}/api/log")
    with pytest.raises(Exception):  # noqa: B017 - FastMCP wraps the ValueError
        await server.call_tool("log_interaction", {"type": "nonsense"})
    assert not route.called


@respx.mock
async def test_get_stats(server_and_client) -> None:
    server, _ = server_and_client
    route = respx.get(f"{API_BASE}/api/stats").mock(
        return_value=httpx.Response(200, json={"events": 42, "nodes": 10})
    )
    await server.call_tool("get_stats", {})
    _assert_authed(route, "GET", "/api/stats")


@respx.mock
async def test_validate_key_hits_endpoint_with_header() -> None:
    route = respx.get(f"{API_BASE}/api/keys/validate").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )
    async with BrainClient(API_BASE, API_KEY) as client:
        result = await client.validate_key()
    assert result == {"valid": True}
    request = route.calls.last.request
    assert request.headers.get("x-api-key") == API_KEY


# --- error mapping ---------------------------------------------------------
@respx.mock
async def test_invalid_key_maps_to_auth_error() -> None:
    respx.get(f"{API_BASE}/api/keys/validate").mock(
        return_value=httpx.Response(401, json={"detail": "invalid key"})
    )
    async with BrainClient(API_BASE, API_KEY) as client:
        with pytest.raises(BrainAuthError):
            await client.validate_key()


@respx.mock
async def test_brain_unreachable_maps_to_unreachable_error() -> None:
    respx.post(f"{API_BASE}/api/recall").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    async with BrainClient(API_BASE, API_KEY) as client:
        with pytest.raises(BrainUnreachableError):
            await client.recall("anything")


@respx.mock
async def test_server_error_maps_to_response_error() -> None:
    respx.get(f"{API_BASE}/api/stats").mock(
        return_value=httpx.Response(500, json={"detail": "boom"})
    )
    async with BrainClient(API_BASE, API_KEY) as client:
        with pytest.raises(BrainResponseError) as excinfo:
            await client.stats()
    assert excinfo.value.status_code == 500
