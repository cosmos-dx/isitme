"""isitme Brain MCP server.

Exposes your personal "central brain" (captured online behavior + knowledge
graph + learned profile) to any MCP-capable LLM host (Cursor, Claude Desktop,
etc.). The server is a thin, well-typed bridge: every tool calls the local Web
API / BFF (default ``http://127.0.0.1:5050``) authenticated with your
``X-API-Key``. No brain logic lives here.
"""

from __future__ import annotations

__version__ = "0.1.0"

from brain_mcp.config import BrainMCPConfig, ConfigError, load_config
from brain_mcp.server import build_server

__all__ = [
    "BrainMCPConfig",
    "ConfigError",
    "build_server",
    "load_config",
    "__version__",
]
