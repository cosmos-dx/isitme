"""Entrypoint: ``python -m brain_mcp`` (or the ``brain-mcp`` console script).

Loads config (fail-fast on a missing key), validates the key against the Web
API, then runs the FastMCP server over the configured transport (stdio by
default). All diagnostics go to **stderr** — stdout is reserved for the stdio
JSON-RPC stream.
"""

from __future__ import annotations

import asyncio
import logging
import sys

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


async def _validate_key(config: BrainMCPConfig) -> bool:
    """Validate the API key on startup. Returns True if the server may start.

    A rejected key is fatal (returns False); an unreachable brain is a warning
    so the host doesn't crash-loop while the user boots the Web API.
    """
    if config.skip_validation:
        logger.info("Skipping startup key validation (BRAIN_MCP_SKIP_VALIDATION set).")
        return True
    client = BrainClient(config.api_base, config.api_key, timeout=config.timeout)
    try:
        result = await client.validate_key()
        logger.info(
            "API key validated against %s (key %s).", config.api_base, config.key_hint
        )
        if isinstance(result, dict) and result.get("valid") is False:
            logger.error("Web API reports the key is invalid: %s", result)
            return False
        return True
    except BrainAuthError as exc:
        logger.error("%s", exc)
        return False
    except BrainUnreachableError as exc:
        logger.warning(
            "Could not validate key now (%s). Starting anyway; tools will report "
            "errors until the brain is reachable.",
            exc,
        )
        return True
    finally:
        await client.aclose()


def main() -> int:
    _configure_logging()
    try:
        config = load_config()
    except ConfigError as exc:
        print(f"[brain-mcp] configuration error:\n{exc}", file=sys.stderr)
        return 2

    if not asyncio.run(_validate_key(config)):
        print(
            "[brain-mcp] startup aborted: the API key was rejected. "
            "Update BRAIN_API_KEY and restart.",
            file=sys.stderr,
        )
        return 1

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
