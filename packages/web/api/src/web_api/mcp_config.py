"""Builds a ready-to-paste MCP server config (Cursor / Claude Desktop format).

The generated config points an MCP client at *this user's* Core Brain using a
chosen API key. We never persist plaintext keys, so the key is either freshly
minted (returned once), supplied by the caller, or left as a clearly-marked
placeholder for the user to fill in.
"""

from __future__ import annotations

import json
from typing import Any

PLACEHOLDER = "<YOUR_ISITME_API_KEY>"


def build_mcp_config(brain_url: str, api_key: str | None) -> dict[str, Any]:
    key = api_key or PLACEHOLDER
    return {
        "mcpServers": {
            "isitme-brain": {
                "command": "python",
                "args": ["-m", "brain_mcp"],
                "env": {
                    "BRAIN_BASE_URL": brain_url,
                    "BRAIN_API_KEY": key,
                },
            }
        }
    }


def build_snippet(config: dict[str, Any]) -> str:
    return json.dumps(config, indent=2)


def build_instructions(brain_url: str) -> str:
    return (
        "Add this to your MCP client config:\n"
        "  • Cursor:  ~/.cursor/mcp.json (or Settings -> MCP -> Add server)\n"
        "  • Claude Desktop:  claude_desktop_config.json\n\n"
        f"It points the isitme MCP server at your local brain ({brain_url}). "
        "The browser extension and MCP server authenticate to the brain with the "
        "API key above — keep it secret; you can revoke it anytime from the API "
        "Keys panel. If you see the placeholder, generate or paste a real key first."
    )
