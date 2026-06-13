"""Smoke tests: configuration fail-fast and tool registration."""

from __future__ import annotations

import pytest

from brain_mcp.config import (
    DEFAULT_API_BASE,
    BrainMCPConfig,
    ConfigError,
    load_config,
)
from brain_mcp.server import build_server

EXPECTED_TOOLS = {
    "recall_context",
    "search_memory",
    "get_user_profile",
    "ask_brain",
    "log_interaction",
    "get_stats",
}


def _clear_brain_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "BRAIN_API_KEY",
        "BRAIN_API_BASE",
        "BRAIN_BASE_URL",
        "BRAIN_API_TIMEOUT",
        "BRAIN_MCP_TRANSPORT",
        "BRAIN_MCP_HOST",
        "BRAIN_MCP_PORT",
        "BRAIN_MCP_SKIP_VALIDATION",
    ):
        monkeypatch.delenv(var, raising=False)


def test_load_config_fails_fast_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_brain_env(monkeypatch)
    with pytest.raises(ConfigError) as excinfo:
        load_config(load_dotenv_files=False)
    assert "BRAIN_API_KEY" in str(excinfo.value)


def test_load_config_defaults_and_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_brain_env(monkeypatch)
    monkeypatch.setenv("BRAIN_API_KEY", "isme_test_key")
    cfg = load_config(load_dotenv_files=False)
    assert cfg.api_key == "isme_test_key"
    assert cfg.api_base == DEFAULT_API_BASE
    assert cfg.transport == "stdio"

    # BRAIN_BASE_URL is honored as an alias; trailing slash stripped.
    monkeypatch.setenv("BRAIN_BASE_URL", "http://example.test:5050/")
    cfg2 = load_config(load_dotenv_files=False)
    assert cfg2.api_base == "http://example.test:5050"

    # BRAIN_API_BASE takes precedence over the alias.
    monkeypatch.setenv("BRAIN_API_BASE", "http://primary.test:9000")
    cfg3 = load_config(load_dotenv_files=False)
    assert cfg3.api_base == "http://primary.test:9000"


def test_load_config_rejects_bad_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_brain_env(monkeypatch)
    monkeypatch.setenv("BRAIN_API_KEY", "isme_test_key")
    monkeypatch.setenv("BRAIN_MCP_TRANSPORT", "carrier-pigeon")
    with pytest.raises(ConfigError):
        load_config(load_dotenv_files=False)


def _config() -> BrainMCPConfig:
    return BrainMCPConfig(api_key="isme_test_key", api_base="http://brain.test:5050")


async def test_all_tools_registered_with_schemas() -> None:
    server = build_server(_config())
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOLS

    by_name = {t.name: t for t in tools}
    for tool in tools:
        assert tool.description, f"{tool.name} is missing a description"
        assert tool.inputSchema.get("type") == "object"

    # Spot-check a couple of schemas.
    recall = by_name["recall_context"]
    assert "query" in recall.inputSchema["properties"]
    assert "query" in recall.inputSchema.get("required", [])
    assert "k" in recall.inputSchema["properties"]

    log = by_name["log_interaction"]
    assert "type" in log.inputSchema["properties"]
    assert "type" in log.inputSchema.get("required", [])


def test_server_name() -> None:
    server = build_server(_config())
    assert server.name == "isitme-brain"
