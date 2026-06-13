"""Configuration for the Brain MCP server.

Everything is read from the environment (and an optional ``.env``). There are no
required secrets: authentication is via a one-time interactive Google login
(``python -m brain_mcp login``) whose tokens are cached on disk, so a host can
launch the server with **zero** env vars (localhost defaults apply).

Env vars
--------
* ``BRAIN_API_BASE``  (optional) — Web API base URL. Default ``http://127.0.0.1:5050``.
                      ``BRAIN_BASE_URL`` is accepted as an alias for compatibility
                      with configs minted by the Web API.
* ``BRAIN_API_TIMEOUT`` (optional) — per-request timeout in seconds. Default ``20``.
* ``BRAIN_CREDENTIALS_PATH`` (optional) — where the OAuth token cache lives.
                      Default ``~/.isitme/credentials.json``.
* ``BRAIN_OAUTH_REDIRECT_PORT`` (optional) — loopback port used by the
                      ``login`` flow's redirect (``http://127.0.0.1:<port>/callback``).
                      Default ``8765``. Register the matching redirect URI in
                      Google Cloud.
* ``BRAIN_MCP_TRANSPORT`` (optional) — ``stdio`` (default), ``sse`` or
                      ``streamable-http``.
* ``BRAIN_MCP_HOST`` / ``BRAIN_MCP_PORT`` (optional) — bind address for the HTTP
                      transports. Default ``127.0.0.1:8088``.
* ``BRAIN_MCP_SKIP_VALIDATION`` (optional) — set truthy to skip the startup auth
                      handshake (useful for offline/dev).

``OAUTH_CLIENT_JSON`` (the Web API's Google client, loaded from the repo-root
``.env``) is read by the ``login`` flow to obtain the client_id/secret.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_API_BASE = "http://127.0.0.1:5050"
DEFAULT_TIMEOUT = 20.0
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8088
DEFAULT_OAUTH_REDIRECT_PORT = 8765
DEFAULT_CREDENTIALS_PATH = Path.home() / ".isitme" / "credentials.json"
VALID_TRANSPORTS = ("stdio", "sse", "streamable-http")

_TRUTHY = {"1", "true", "yes", "on"}


class ConfigError(RuntimeError):
    """Raised when the server is misconfigured (e.g. an invalid transport)."""


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

    api_base: str = DEFAULT_API_BASE
    timeout: float = DEFAULT_TIMEOUT
    transport: str = "stdio"
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    skip_validation: bool = False
    credentials_path: Path = field(default_factory=lambda: DEFAULT_CREDENTIALS_PATH)
    oauth_redirect_port: int = DEFAULT_OAUTH_REDIRECT_PORT


def load_config(*, load_dotenv_files: bool = True) -> BrainMCPConfig:
    """Build a :class:`BrainMCPConfig` from the environment.

    Raises :class:`ConfigError` (with an actionable message) when a value is
    invalid. There are no required secrets — auth is handled by the cached
    Google login.
    """
    if load_dotenv_files:
        _load_env_files()

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
    redirect_port = int(
        _parse_float("BRAIN_OAUTH_REDIRECT_PORT", float(DEFAULT_OAUTH_REDIRECT_PORT))
    )

    creds_env = (os.environ.get("BRAIN_CREDENTIALS_PATH") or "").strip()
    credentials_path = (
        Path(creds_env).expanduser() if creds_env else DEFAULT_CREDENTIALS_PATH
    )

    return BrainMCPConfig(
        api_base=api_base,
        timeout=timeout,
        transport=transport,
        host=host,
        port=port,
        skip_validation=_is_truthy(os.environ.get("BRAIN_MCP_SKIP_VALIDATION")),
        credentials_path=credentials_path,
        oauth_redirect_port=redirect_port,
    )


def _parse_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid number.") from exc
