"""Configuration for the Brain MCP server.

Everything is read from the environment (and an optional ``.env``). The only
required value is the API key; all other knobs have safe localhost defaults so a
host can launch the server with a single env var.

Env vars
--------
* ``BRAIN_API_KEY``   (required) — plaintext ``X-API-Key`` issued by the Web API.
* ``BRAIN_API_BASE``  (optional) — Web API base URL. Default ``http://127.0.0.1:5050``.
                      ``BRAIN_BASE_URL`` is accepted as an alias for compatibility
                      with configs minted by the Web API.
* ``BRAIN_API_TIMEOUT`` (optional) — per-request timeout in seconds. Default ``20``.
* ``BRAIN_MCP_TRANSPORT`` (optional) — ``stdio`` (default), ``sse`` or
                      ``streamable-http``.
* ``BRAIN_MCP_HOST`` / ``BRAIN_MCP_PORT`` (optional) — bind address for the HTTP
                      transports. Default ``127.0.0.1:8088``.
* ``BRAIN_MCP_SKIP_VALIDATION`` (optional) — set truthy to skip the startup key
                      validation handshake (useful for offline/dev).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_API_BASE = "http://127.0.0.1:5050"
DEFAULT_TIMEOUT = 20.0
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8088
VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")

_TRUTHY = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    """Raised when the server is misconfigured (e.g. missing API key)."""


def _find_repo_root(start: Path | None = None) -> Path | None:
    """Walk upward to find a directory containing ``.git`` (repo root)."""
    here = (start or Path(__file__).resolve()).parent
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _load_env_files() -> None:
    """Load ``.env`` from CWD and the repo root (without overriding real env)."""
    load_dotenv(Path.cwd() / ".env")
    repo_root = _find_repo_root()
    if repo_root is not None:
        load_dotenv(repo_root / ".env")


def _is_truthy(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in _TRUTHY


@dataclass(frozen=True)
class BrainMCPConfig:
    """Validated configuration for the Brain MCP server."""

    api_key: str
    api_base: str = DEFAULT_API_BASE
    timeout: float = DEFAULT_TIMEOUT
    transport: str = "stdio"
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    skip_validation: bool = False

    @property
    def key_hint(self) -> str:
        """Non-secret prefix of the key, safe to print in logs/errors."""
        return f"{self.api_key[:8]}…" if len(self.api_key) > 8 else "set"


def load_config(*, load_dotenv_files: bool = True) -> BrainMCPConfig:
    """Build a :class:`BrainMCPConfig` from the environment.

    Raises :class:`ConfigError` (with an actionable message) when required
    values are missing or invalid. This is intentionally *fail-fast* so a
    misconfigured MCP host surfaces the problem immediately at launch.
    """
    if load_dotenv_files:
        _load_env_files()

    api_key = (os.environ.get("BRAIN_API_KEY") or "").strip()
    if not api_key:
        raise ConfigError(
            "BRAIN_API_KEY is not set.\n"
            "  Create a key in the isitme dashboard (API Keys panel) and expose it "
            "to this MCP server, e.g.\n"
            '    "env": { "BRAIN_API_KEY": "isme_..." }\n'
            "  in your MCP client config, or `export BRAIN_API_KEY=isme_...` in the shell."
        )

    # Primary name is BRAIN_API_BASE; BRAIN_BASE_URL is accepted as an alias so
    # configs minted by the Web API keep working.
    api_base = (
        os.environ.get("BRAIN_API_BASE")
        or os.environ.get("BRAIN_BASE_URL")
        or DEFAULT_API_BASE
    ).strip().rstrip("/")

    timeout = _parse_float("BRAIN_API_TIMEOUT", DEFAULT_TIMEOUT)
    if timeout <= 0:
        raise ConfigError("BRAIN_API_TIMEOUT must be a positive number of seconds.")

    transport = (os.environ.get("BRAIN_MCP_TRANSPORT") or "stdio").strip().lower()
    if transport not in VALID_TRANSPORTS:
        raise ConfigError(
            f"BRAIN_MCP_TRANSPORT={transport!r} is invalid. "
            f"Choose one of: {', '.join(VALID_TRANSPORTS)}."
        )

    host = (os.environ.get("BRAIN_MCP_HOST") or DEFAULT_HOST).strip()
    port = int(_parse_float("BRAIN_MCP_PORT", float(DEFAULT_PORT)))

    return BrainMCPConfig(
        api_key=api_key,
        api_base=api_base,
        timeout=timeout,
        transport=transport,
        host=host,
        port=port,
        skip_validation=_is_truthy(os.environ.get("BRAIN_MCP_SKIP_VALIDATION")),
    )


def _parse_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid number.") from exc
