# brain-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes your personal
**isitme central brain** — your captured online behavior, knowledge graph,
semantic memories, and learned profile — to any MCP-capable LLM host (Cursor,
Claude Desktop, etc.).

It is a thin, typed bridge: every tool calls the local **Web API / BFF**
(default `http://127.0.0.1:5050`) authenticated with a **Google OAuth token**
(`Authorization: Bearer <id_token>`). No brain logic lives here — the Web API
owns auth and the Core Brain owns cognition.

```
LLM host (Cursor / Claude) ──stdio/http──> brain-mcp ──Bearer <google id_token>──> Web API (5050) ──> Core Brain
```

Authentication is a **one-time interactive Google sign-in** (`python -m
brain_mcp login`). Tokens are cached at `~/.isitme/credentials.json` (chmod
`600`) and **refreshed automatically** — there is no API key to manage.

## Tools

| Tool | Endpoint | What it does |
| --- | --- | --- |
| `recall_context(query, k=5)` | `POST /api/recall` | Memories most relevant to a query. |
| `search_memory(query, k=8)` | `POST /api/search` | Broader semantic search across the brain. |
| `get_user_profile()` | `GET /api/profile` | The user's learned mindset/behavior model. |
| `ask_brain(question, k=6)` | `POST /api/ask` | Synthesized, brain-grounded answer + sources. |
| `log_interaction(type, content?, url?, title?, data?)` | `POST /api/log` | Write an interaction/opinion back into the brain. |
| `get_stats()` | `GET /api/stats` | Brain size/health counters. |

`log_interaction`'s `type` must be one of: `visit`, `click`, `dwell`, `link`,
`search`, `llm_chat`, `content_create`, `opinion` (use `opinion` to capture a
stated belief/preference). Events are tagged `source: "mcp"`.

## Install

Requires Python 3.11+.

```bash
cd packages/brain-mcp
python3.13 -m venv .venv
.venv/bin/python -m pip install -e .          # add '.[http]' for the HTTP transport
.venv/bin/python -m pip install -e '.[dev]'   # for tests/lint
```

## Configure

The only **required** setting is your API key. Create one in the isitme
dashboard (**API Keys** panel) and expose it to the server:

| Env var | Required | Default | Notes |
| --- | --- | --- | --- |
| `BRAIN_API_KEY` | ✅ | — | Plaintext `X-API-Key`. |
| `BRAIN_API_BASE` | | `http://127.0.0.1:5050` | Web API base URL (`BRAIN_BASE_URL` is an alias). |
| `BRAIN_API_TIMEOUT` | | `20` | Per-request timeout (seconds). |
| `BRAIN_MCP_TRANSPORT` | | `stdio` | `stdio` \| `sse` \| `streamable-http`. |
| `BRAIN_MCP_HOST` / `BRAIN_MCP_PORT` | | `127.0.0.1` / `8088` | Bind address for HTTP transports. |
| `BRAIN_MCP_SKIP_VALIDATION` | | off | Skip the startup key handshake (offline/dev). |

You can set these in the MCP client's `env` block (recommended), `export` them,
or put them in a `.env` (loaded from the CWD and repo root — see `.env.example`).

On startup the server **validates the key** via `GET /api/keys/validate`:
- Missing key → fails fast with copy-paste guidance.
- Rejected key → exits with an actionable message.
- Brain unreachable → warns and starts anyway (tools report a clear error until
  the Web API is up).

## Run

```bash
# stdio (default — how MCP hosts launch it):
BRAIN_API_KEY=isme_... .venv/bin/python -m brain_mcp

# optional long-lived Streamable HTTP server on 127.0.0.1:8088:
BRAIN_API_KEY=isme_... BRAIN_MCP_TRANSPORT=streamable-http .venv/bin/python -m brain_mcp
```

## Connectors (ready to paste)

Replace `<YOUR_ISITME_API_KEY>` with a key from the dashboard. Example files live
in [`connectors/`](./connectors). The `command` below uses this repo's venv;
swap in any Python that has `brain-mcp` installed (or the `brain-mcp` console
script).

### Cursor — `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "isitme-brain": {
      "command": "/Users/abhishekgupta/code/personal/isitme/packages/brain-mcp/.venv/bin/python",
      "args": ["-m", "brain_mcp"],
      "env": {
        "BRAIN_API_KEY": "<YOUR_ISITME_API_KEY>",
        "BRAIN_API_BASE": "http://127.0.0.1:5050"
      }
    }
  }
}
```

### Claude Desktop — `claude_desktop_config.json`

(macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "isitme-brain": {
      "command": "/Users/abhishekgupta/code/personal/isitme/packages/brain-mcp/.venv/bin/python",
      "args": ["-m", "brain_mcp"],
      "env": {
        "BRAIN_API_KEY": "<YOUR_ISITME_API_KEY>",
        "BRAIN_API_BASE": "http://127.0.0.1:5050"
      }
    }
  }
}
```

### Generic stdio MCP client

```json
{
  "mcpServers": {
    "isitme-brain": {
      "command": "python",
      "args": ["-m", "brain_mcp"],
      "env": {
        "BRAIN_API_KEY": "<YOUR_ISITME_API_KEY>",
        "BRAIN_API_BASE": "http://127.0.0.1:5050",
        "BRAIN_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

### Optional: HTTP transport

Run the server as a long-lived process with
`BRAIN_MCP_TRANSPORT=streamable-http` (requires `pip install -e '.[http]'`), then
point an HTTP-capable MCP client at `http://127.0.0.1:8088/mcp`:

```json
{
  "mcpServers": {
    "isitme-brain": { "url": "http://127.0.0.1:8088/mcp" }
  }
}
```

After editing a config, restart the host (Cursor: reload MCP from Settings →
MCP). The brain tools then appear to the model automatically.

## Tests

```bash
.venv/bin/python -m pytest         # from packages/brain-mcp
.venv/bin/ruff check .
```

- `tests/test_server.py` — smoke test: the server constructs and all six tools
  are registered with schemas; config fails fast without a key.
- `tests/test_tools_http.py` — mocks the HTTP layer (`respx`) and asserts each
  tool hits the right endpoint with the `X-API-Key` header.
