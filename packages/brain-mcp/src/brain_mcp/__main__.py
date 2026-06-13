"""Entrypoint: ``python -m brain_mcp`` (or the ``brain-mcp`` console script).

Two modes:

* ``python -m brain_mcp login`` — run the one-time interactive Google OAuth flow
  and cache tokens under ``~/.isitme/credentials.json`` (see :mod:`brain_mcp.auth`).
* ``python -m brain_mcp`` (default) — load config, do a best-effort auth
  handshake, then run the FastMCP server over the configured transport (stdio by
  default). All diagnostics go to **stderr** — stdout is reserved for the stdio
  JSON-RPC stream.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from brain_mcp import auth
from brain_mcp.auth import LoginError, NotAuthenticatedError, TokenProvider
from brain_mcp.client import (
    BrainAuthError,
    BrainClient,
    BrainUnreachableError,
)
from brain_mcp.config import BrainMCPConfig, ConfigError, load_config
from brain_mcp.server import build_server

logger = logging.getLogger("brain_mcp")


def _configure_logging() -> None:
    # stderr only: stdout carries the stdio transport's JSON-RPC frames.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _run_login(config: BrainMCPConfig) -> int:
    """Run ``python -m brain_mcp login`` — interactive Google OAuth."""
    try:
        client_info = auth.resolve_oauth_client(api_base=config.api_base)
    except LoginError as exc:
        print(f"[brain-mcp] login error:\n{exc}", file=sys.stderr)
        return 2
    try:
        creds = auth.login(
            client_info,
            path=config.credentials_path,
            port=config.oauth_redirect_port,
        )
    except LoginError as exc:
        print(f"[brain-mcp] login failed:\n{exc}", file=sys.stderr)
        return 1
    who = creds.email or "your Google account"
    print(
        f"\n[brain-mcp] Logged in as {who}. "
        f"Credentials cached at {config.credentials_path} (chmod 600).\n"
        "You can now start the MCP server: python -m brain_mcp"
    )
    return 0


async def _validate_auth(config: BrainMCPConfig) -> None:
    """Best-effort startup auth handshake against ``GET /auth/me``.

    Never aborts startup: a missing login or unreachable brain is logged as a
    warning so the host doesn't crash-loop. Tools surface an actionable error on
    first use until the user runs ``python -m brain_mcp login``.
    """
    if config.skip_validation:
        logger.info("Skipping startup auth handshake (BRAIN_MCP_SKIP_VALIDATION set).")
        return
    provider = TokenProvider(config.credentials_path)
    try:
        await provider.id_token()
    except NotAuthenticatedError:
        logger.warning(
            "Not logged in yet. Run `python -m brain_mcp login`. Starting anyway; "
            "tools will report an auth error until you do."
        )
        await provider.aclose()
        return
    client = BrainClient(config.api_base, provider.id_token, timeout=config.timeout)
    try:
        result = await client.whoami()
        user = (result or {}).get("user") or {}
        logger.info(
            "Authenticated to %s as %s.",
            config.api_base,
            user.get("email") or user.get("id") or "a Google user",
        )
    except BrainAuthError as exc:
        logger.warning("%s", exc)
    except BrainUnreachableError as exc:
        logger.warning(
            "Could not reach the Web API to validate auth now (%s). Starting anyway.",
            exc,
        )
    finally:
        await client.aclose()


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = sys.argv[1:] if argv is None else argv

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"[brain-mcp] configuration error:\n{exc}", file=sys.stderr)
        return 2

    if args and args[0] == "login":
        return _run_login(config)
    if args and args[0] in ("-h", "--help", "help"):
        print(
            "Usage:\n"
            "  python -m brain_mcp          Run the MCP server (stdio by default).\n"
            "  python -m brain_mcp login    One-time Google sign-in (caches tokens).",
            file=sys.stderr,
        )
        return 0

    asyncio.run(_validate_auth(config))

    server = build_server(config)
    logger.info(
        "Starting isitme Brain MCP server (transport=%s, brain=%s).",
        config.transport,
        config.api_base,
    )
    if config.transport in ("sse", "streamable-http"):
        logger.info("HTTP transport listening on %s:%s", config.host, config.port)

    try:
        server.run(transport=config.transport)
    except KeyboardInterrupt:  # pragma: no cover - interactive
        logger.info("Shutting down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
