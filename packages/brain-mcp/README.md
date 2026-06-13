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

## Sign in (one-time)

Authenticate once with Google; tokens are cached and refreshed automatically.

```bash
.venv/bin/python -m brain_mcp login
```

This opens your browser to Google sign-in, captures the result on a **loopback
redirect** (`http://127.0.0.1:8765/callback` by default), exchanges the code for
tokens, and writes them to `~/.isitme/credentials.json` (chmod `600`). The MCP
server then attaches `Authorization: Bearer <id_token>` to every Web-API call
and **refreshes** the token via Google when it expires.

> **Google Cloud setup (one-time):** the loopback redirect URI must be
> registered on the OAuth **web** client referenced by `OAUTH_CLIENT_JSON` in the
> repo-root `.env`:
>
> 1. **Google Cloud Console → APIs & Services → Credentials** → open that OAuth
>    client.
> 2. Under **Authorized redirect URIs**, add `http://127.0.0.1:8765/callback`
>    (or whatever `BRAIN_OAUTH_REDIRECT_PORT` you choose). Web clients require an
>    **exact** match, so the port is fixed — or switch the client type to
>    **Desktop app**, which allows any loopback port.
> 3. The OAuth consent screen is in **Testing**, so add your Google account
>    under **OAuth consent screen → Test users**.
> 4. Ensure the **openid / email / profile** scopes are enabled (the default
>    consent set).
>
> The CLI reads the `client_id` **and** `client_secret` from `OAUTH_CLIENT_JSON`
> (the same value the Web API uses) to exchange the code; the Web API itself only
> exposes the non-secret `client_id` at `GET /auth/oauth-config`.

## Configure

There are **no required secrets** — auth is the cached Google login above. All
knobs are optional with safe localhost defaults:

| Env var | Default | Notes |
| --- | --- | --- |
| `BRAIN_API_BASE` | `http://127.0.0.1:5050` | Web API base URL (`BRAIN_BASE_URL` is an alias). |
| `BRAIN_API_TIMEOUT` | `20` | Per-request timeout (seconds). |
| `BRAIN_CREDENTIALS_PATH` | `~/.isitme/credentials.json` | Where the OAuth token cache lives. |
| `BRAIN_OAUTH_REDIRECT_PORT` | `8765` | Loopback port for the `login` redirect. |
| `BRAIN_MCP_TRANSPORT` | `stdio` | `stdio` \| `sse` \| `streamable-http`. |
| `BRAIN_MCP_HOST` / `BRAIN_MCP_PORT` | `127.0.0.1` / `8088` | Bind address for HTTP transports. |
| `BRAIN_MCP_SKIP_VALIDATION` | off | Skip the startup auth handshake (offline/dev). |

You can set these in the MCP client's `env` block, `export` them, or put them in
a `.env` (loaded from the CWD and repo root — see `.env.example`).

On startup the server does a best-effort auth handshake via `GET /auth/me`:
- Not logged in → warns to run `python -m brain_mcp login`; starts anyway (tools
  return an actionable error until you log in).
- Token rejected / brain unreachable → warns and starts anyway.

## Run

```bash
# stdio (default — how MCP hosts launch it):
.venv/bin/python -m brain_mcp

# optional long-lived Streamable HTTP server on 127.0.0.1:8088:
BRAIN_MCP_TRANSPORT=streamable-http .venv/bin/python -m brain_mcp
```

## Connectors (ready to paste)

No API key needed — just run `python -m brain_mcp login` once, then use any of
these. Example files live in [`connectors/`](./connectors). The `command` below
uses this repo's venv; swap in any Python that has `brain-mcp` installed (or the
`brain-mcp` console script).

### Cursor — `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "isitme-brain": {
      "command": "/Users/abhishekgupta/code/personal/isitme/packages/brain-mcp/.venv/bin/python",
      "args": ["-m", "brain_mcp"],
      "env": {
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
        "BRAIN_API_BASE": "http://127.0.0.1:5050",
        "BRAIN_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

### Optional: HTTP transport

Sign in once (`python -m brain_mcp login`), then run the server as a long-lived
process with `BRAIN_MCP_TRANSPORT=streamable-http` (requires `pip install -e
'.[http]'`), then point an HTTP-capable MCP client at `http://127.0.0.1:8088/mcp`:

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
  are registered with schemas; config loads with no env (no key required).
- `tests/test_tools_http.py` — mocks the HTTP layer (`respx`) and the token
  provider, asserting each tool hits the right endpoint with an
  `Authorization: Bearer <id_token>` header (and that auth/transport errors map
  to the right exceptions).
- `tests/test_auth.py` — the OAuth token layer: credential persistence (chmod
  600), `TokenProvider` (valid / expired-and-refreshed / missing), and OAuth
  client resolution from `OAUTH_CLIENT_JSON`.
