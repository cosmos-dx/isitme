# isitme — Deployment & Operations

A practical operator guide for running `isitme` locally, enabling the optional
scalable backends, and deploying the MCP server and browser extension. Read
[ARCHITECTURE.md](./ARCHITECTURE.md) first for how the pieces fit together.

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Secrets & `.env`](#2-secrets--env)
3. [Ports (and why they're fixed)](#3-ports-and-why-theyre-fixed)
4. [Run everything locally](#4-run-everything-locally)
5. [Run each service individually](#5-run-each-service-individually)
6. [Docker & scalable backends](#6-docker--scalable-backends)
7. [Deploying the MCP server](#7-deploying-the-mcp-server)
8. [Deploying the browser extension](#8-deploying-the-browser-extension)
9. [Google Cloud Console setup](#9-google-cloud-console-setup)
10. [Production hardening](#10-production-hardening)
11. [Cross-references](#11-cross-references)

---

## 1. Prerequisites

- **Python 3.11+** (the packages target `>=3.11`).
- **Node 18+** and npm (frontend + extension build).
- **Docker** (optional — only for the scalable backend services).
- A Google Cloud project with an **OAuth web client** (see
  [§9](#9-google-cloud-console-setup)).

The default stack is **fully local-first**: SQLite + in-process numpy vectors +
a hashing embedder. No external services, API keys, or network are required to
run the brain itself.

---

## 2. Secrets & `.env`

Secrets live in a **repo-root `.env`** (gitignored — never commit it). The Web
API walks up to the repo root and loads it (`web_api/config.py`).

```bash
# /Users/abhishekgupta/code/personal/isitme/.env
OAUTH_CLIENT_JSON={"web":{"client_id":"...","client_secret":"...","redirect_uris":["http://localhost:5050/auth/google/callback"],"javascript_origins":["http://localhost:4000"]}}
OPENAI_API_KEY=sk-...        # optional — enriches "Ask your brain" synthesis
```

| Variable | Required | Used by | Notes |
| --- | --- | --- | --- |
| `OAUTH_CLIENT_JSON` | for sign-in | Web API | The Google OAuth **web** client JSON. Its pinned `redirect_uris` / `javascript_origins` are honored exactly — Google rejects mismatches. |
| `OPENAI_API_KEY` | optional | Web API (`/api/ask`) | When set, `/api/ask` answers are synthesized by OpenAI (`synthesized_by: "openai"`); otherwise a zero-network template answer is returned. |

The brain runs **without** any `.env`. The Web API runs without OAuth too, but
sign-in returns `503 Google OAuth is not configured` until `OAUTH_CLIENT_JSON`
is present.

Other (non-secret) knobs have safe defaults and may be overridden with env vars:
`WEB_HOST`, `WEB_PORT`, `WEB_BRAIN_BASE_URL`, `WEB_BRAIN_PUBLIC_URL`,
`WEB_FRONTEND_ORIGIN`, `WEB_DATA_DIR`, `WEB_MONGO_URI`, `WEB_MONGO_DB`,
`WEB_SESSION_SECRET`, `WEB_SESSION_COOKIE`. The Core Brain reads `BRAIN_*`
(nested via `__`) and/or a `config.yaml` — see [`config.example.yaml`](./config.example.yaml).

---

## 3. Ports (and why they're fixed)

| Port | Service | Pinned by |
| --- | --- | --- |
| **4000** | Frontend (React/Vite) | Google OAuth client `javascript_origins=[http://localhost:4000]` |
| **5050** | Web API / BFF (FastAPI) | Google OAuth client `redirect_uris=[http://localhost:5050/auth/google/callback]` |
| **8077** | Core Brain HTTP API | Convention/default (`server.port`, `dev.sh`, `WEB_BRAIN_BASE_URL`); the Web API proxies to it |

> **Do not change 4000 or 5050.** Google validates the redirect URI and JS
> origin against the values registered in the OAuth client; any mismatch yields
> `redirect_uri_mismatch` and sign-in fails. `8077` is the brain's fixed default
> that the Web API points to via `WEB_BRAIN_BASE_URL`.

(The MCP server's *optional* HTTP transport defaults to `8088` — only relevant
if you run it as a long-lived HTTP server instead of stdio.)

---

## 4. Run everything locally

The `packages/web` dev workflow boots all three services at once.

**One-time setup** (from `packages/web/`):

```bash
# 1) Python venv with Web API + Core Brain runtime deps
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ./api "openai>=1.20" \
    "numpy>=1.26" "pyyaml>=6.0" "cryptography>=42.0"

# 2) Frontend + dev orchestrator deps
npm install                 # installs `concurrently`
npm run install:web         # installs packages/web/frontend
```

> The Core Brain is run via `PYTHONPATH` (no separate install); its runtime deps
> are installed into the same venv above.

**Run all three:**

```bash
# from packages/web/
./dev.sh            # or: npm run dev
```

This starts Core Brain `:8077`, Web API `:5050`, and the frontend `:4000`
(via `concurrently`). Open **http://localhost:4000** and click **Sign in with
Google**.

---

## 5. Run each service individually

```bash
# Core Brain (:8077) — from packages/web/
PYTHONPATH=../brain-core/src .venv/bin/python -m brain_core serve --port 8077

# Web API (:5050)
.venv/bin/python -m web_api --port 5050

# Frontend (:4000)
npm --prefix frontend run dev
```

The `brain` CLI also offers:

```bash
brain serve            # run the Core Brain HTTP API
brain stats            # print store counters as JSON and exit
brain sync             # run the standalone outbox → cloud sync worker
```

Seed a few events so the dashboard graph isn't empty (brain must be up):

```bash
curl -s -X POST http://127.0.0.1:8077/v1/ingest \
  -H 'content-type: application/json' \
  -d '{"client":"seed","events":[
        {"type":"search","data":{"query":"vector databases"},"url":"https://google.com/search"},
        {"type":"visit","title":"pgvector","url":"https://github.com/pgvector/pgvector"},
        {"type":"llm_chat","content":"compare pgvector vs qdrant","data":{"model":"gpt-4o"}}
      ]}'
```

---

## 6. Docker & scalable backends

`docker-compose.yml` (repo root) provides **optional** production-grade backends.
The default local setup needs **none** of them. Bring up only what you want and
flip the matching config/env toggles.

```bash
docker compose up -d mongodb                 # one service backs brain + web API
docker compose up -d postgres qdrant neo4j   # the heavier scalable stack
```

| Service | Image | Ports | Enables |
| --- | --- | --- | --- |
| `mongodb` | `mongo:7` | 27017 | event/graph/vector store **and** the Web API store |
| `postgres` | `postgres:16` | 5432 | event/graph store (drop-in via DSN) |
| `qdrant` | `qdrant/qdrant` | 6333/6334 | vector store (ANN) |
| `neo4j` | `neo4j:5` | 7474/7687 | native graph store (roadmap adapter) |

### MongoDB (the simplest scalable option)

One Mongo instance backs both tiers. Core Brain (`config.yaml` **or** `BRAIN_*`
env):

```yaml
storage:
  event_backend: "mongodb"
  graph_backend: "mongodb"
  vector_backend: "mongodb"     # backends may be mixed, e.g. mongo graph + numpy vectors
  mongo_uri: "mongodb://localhost:27017"
  mongo_db: "isitme"
```

```bash
# equivalently, no file needed:
BRAIN_STORAGE__EVENT_BACKEND=mongodb \
BRAIN_STORAGE__GRAPH_BACKEND=mongodb \
BRAIN_STORAGE__VECTOR_BACKEND=mongodb \
BRAIN_STORAGE__MONGO_URI=mongodb://localhost:27017 \
brain serve
```

Web API store → MongoDB:

```bash
WEB_MONGO_URI=mongodb://localhost:27017   # unset → SQLite (zero setup)
WEB_MONGO_DB=isitme
```

### Postgres / Qdrant / Neo4j

```yaml
storage:
  event_backend: "postgres"
  graph_backend: "postgres"
  postgres_dsn: "postgresql+asyncpg://brain:brain@localhost:5432/brain"
  vector_backend: "qdrant"
  qdrant_url: "http://localhost:6333"
  # graph_backend: "neo4j"; neo4j_uri: "bolt://localhost:7687"   # adapter is roadmap
```

> **Bundled vs roadmap.** `mongodb` and `chroma` vector backends and the
> `postgres` DSN path are wired in `factory.py` today. `qdrant`/`pgvector`
> vectors and `neo4j`/`kuzu` graphs are valid config values but raise
> `NotImplementedError` until their adapter is added (implement the matching ABC
> in `storage/` and a branch in `factory.py`). Install extras as needed:
> `pip install -e "packages/brain-core[postgres]"` (asyncpg),
> `[chroma]`, `[mongo]`, `[embeddings]` (sentence-transformers), `[openai]`.

### npm private-registry gotcha

If your shell/global npm points at a **private registry**, installs of the
frontend or extension can fail with **`401 Unauthorized`**. The project pins the
public registry via committed `.npmrc` files
(`registry=https://registry.npmjs.org/`) in `packages/web`,
`packages/web/frontend`, and `packages/browser-extension`. Run `npm install`
**from those directories** so the project `.npmrc` is honored. If you still see
401s, ensure no global `~/.npmrc` overrides the registry for these installs.

---

## 7. Deploying the MCP server

The MCP server (`packages/brain-mcp`) is a thin, typed bridge: every tool calls
the local Web API, which authenticates the request and proxies to the Core
Brain. No brain logic or secrets live in the MCP process.

```
LLM host (Cursor / Claude) ──stdio/http──▶ brain-mcp ──auth──▶ Web API (5050) ──▶ Core Brain (8077)
```

### Install

```bash
cd packages/brain-mcp
python3 -m venv .venv
.venv/bin/python -m pip install -e .            # add '.[http]' for the HTTP transport
.venv/bin/python -m pip install -e '.[dev]'     # for tests/lint
```

### One-time Google OAuth `login` (no API keys)

The documented authentication path is **Google OAuth** — sign in once and the
MCP server reuses the resulting bearer token (sent as
`Authorization: Bearer <Google OAuth token>`), which the Web API verifies
against Google to resolve your user. This replaces minting/pasting long-lived
API keys.

```bash
# one-time interactive sign-in; the resulting token is cached for the server
brain-mcp login
```

> **Legacy API-key path (still present).** The current code also supports
> `BRAIN_API_KEY` (`X-API-Key`) — minted in the dashboard (**API Keys** panel)
> and validated on startup against `GET /api/keys/validate`. Use it only if you
> have not yet moved to OAuth. Connection knobs (`BRAIN_API_BASE`, default
> `http://127.0.0.1:5050`; `BRAIN_API_TIMEOUT`; `BRAIN_MCP_TRANSPORT`;
> `BRAIN_MCP_HOST`/`PORT`; `BRAIN_MCP_SKIP_VALIDATION`) are unchanged.

### Connector configs

**Cursor** — `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "isitme-brain": {
      "command": "/Users/abhishekgupta/code/personal/isitme/packages/brain-mcp/.venv/bin/python",
      "args": ["-m", "brain_mcp"],
      "env": { "BRAIN_API_BASE": "http://127.0.0.1:5050" }
    }
  }
}
```

**Claude Desktop** — `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS): same `mcpServers` block as above.

**Generic stdio client**: `command: "python"`, `args: ["-m", "brain_mcp"]`,
optionally `"BRAIN_MCP_TRANSPORT": "stdio"`.

**Optional HTTP transport** — run a long-lived server and point HTTP-capable
clients at it:

```bash
BRAIN_MCP_TRANSPORT=streamable-http .venv/bin/python -m brain_mcp   # listens on 127.0.0.1:8088
```

```json
{ "mcpServers": { "isitme-brain": { "url": "http://127.0.0.1:8088/mcp" } } }
```

Ready-to-paste examples live in
[`packages/brain-mcp/connectors/`](./packages/brain-mcp/connectors). After
editing a config, restart/reload the host (Cursor: Settings → MCP). The Web API
can also generate a config for you: `GET /api/mcp-config`.

---

## 8. Deploying the browser extension

### Build `dist/`

```bash
cd packages/browser-extension
npm install            # uses the public registry via project .npmrc
npm run build          # typecheck (tsc --noEmit) + esbuild bundle -> dist/
# npm run dev          # rebuild-on-change (watch)
# npm run zip          # build + isitme-extension.zip for the Web Store
```

`dist/` is dependency-free at runtime: `manifest.json`, bundled
`background.js`/`content.js`, `popup.*`, `options.*`, and generated `icons/`.

### Load unpacked (dev)

1. Open `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** → select `packages/browser-extension/dist/`.
3. Copy the extension **ID** from its card — you need it for OAuth
   ([§9](#9-google-cloud-console-setup)).
4. Open **Options** and set the **API base URL** (`http://127.0.0.1:5050`), then
   **Sign in with Google** in the popup. (The documented auth path is the Google
   OAuth bearer token; pasting a legacy API key still works as a fallback.)

### Chrome Web Store (summary)

Full guide: [`packages/browser-extension/PUBLISHING.md`](./packages/browser-extension/PUBLISHING.md).
In brief:

- Create a developer account (one-time **US$5** fee).
- `npm run zip` — the ZIP root must contain `manifest.json` (not nested under
  `dist/`); bump `version` in `package.json` each upload.
- Prepare listing assets: 128×128 icon, ≥1 screenshot (1280×800), description
  that **plainly states it captures browsing activity** to the user's own server.
- Complete **Privacy practices**: single purpose, per-permission justifications
  (incl. `<all_urls>`), data-usage disclosures (web browsing activity + PII),
  **Limited Use** certification, and a live **privacy policy URL**.
- A **published** extension has a stable ID, so its
  `https://<EXTENSION_ID>.chromiumapp.org/` redirect URI is fixed — register it
  in the OAuth client before release.

---

## 9. Google Cloud Console setup

Required for any Google sign-in (dashboard, extension, MCP).

1. **OAuth consent screen** (APIs & Services → OAuth consent screen):
   configure it; while in **Testing**, **add each Google account that will sign
   in as a Test user** (otherwise sign-in returns `access_denied`). Scopes used
   are non-sensitive: `openid email profile`.
2. **Credentials → OAuth web client** (`OAUTH_CLIENT_JSON` in root `.env`):
   - **Authorized JavaScript origins**: `http://localhost:4000`
   - **Authorized redirect URIs** must include:
     - `http://localhost:5050/auth/google/callback` (Web API dashboard login)
     - `https://<EXTENSION_ID>.chromiumapp.org/` (browser extension — the
       Options page prints the exact URI; add the unpacked-dev ID and, later,
       the published ID)
     - the **MCP loopback** redirect URI used by the `brain-mcp login` flow
       (e.g. `http://127.0.0.1:<port>/` / `http://localhost:<port>/callback`) if
       your MCP OAuth login uses a loopback listener
3. To allow non-test users, move the consent screen to **In production**
   (Publish). Adding sensitive/restricted scopes later may require Google app
   verification.

If you see **`redirect_uri_mismatch`**, the URI/port the client sent does not
exactly match a registered redirect URI — keep ports **4000/5050** and register
the exact `chromiumapp.org` / loopback URIs.

---

## 10. Production hardening

Although `isitme` is designed to run locally, if you expose any tier beyond
`localhost`:

- **HTTPS everywhere.** Terminate TLS in front of the Web API; serve the
  frontend over HTTPS. Then set the session cookie to `https_only=True` and
  consider `SameSite=Strict` (currently `Lax`/`https_only=False` for local dev),
  and update the OAuth client's redirect URIs/origins to the HTTPS hosts.
- **Cloud sync target.** Set `mode: cloud_sync` + `cloud.endpoint` only with a
  trusted server. Always configure `cloud.encryption_key` (Fernet) and **back it
  up** — without it, synced data cannot be decrypted. Payloads are encrypted at
  rest before leaving the machine.
- **Secrets management.** Keep `OAUTH_CLIENT_JSON`, `OPENAI_API_KEY`, the
  session secret (`./.brain/web/session_secret.key`), and the sync key out of
  version control (already gitignored); inject via a secrets manager in
  production. Rotate the OAuth client secret and revoke any legacy API keys you
  no longer use.
- **Scaling the storage tiers.** Move events/graph to Postgres or MongoDB and
  vectors to Qdrant/pgvector/Atlas `$vectorSearch` (see
  [ARCHITECTURE.md §6](./ARCHITECTURE.md#6-fast-traversal--scalability)). Run
  managed instances with auth, backups, and the indexes the stores create on
  `init()` (`(type,key)`, `(src,dst,relation)`, `timestamp`, `session_id`).
- **Process supervision.** Run the brain, Web API, and (if HTTP) the MCP server
  under a supervisor (systemd / a container orchestrator) with health checks on
  `/healthz`. Lock down CORS `allow_origins` to your real frontend origin.

---

## 11. Cross-references

- System architecture → [ARCHITECTURE.md](./ARCHITECTURE.md)
- Validation, troubleshooting & skills → [VALIDATION_AND_SKILLS.md](./VALIDATION_AND_SKILLS.md)
- Run-the-web-product details → [`packages/web/README.md`](./packages/web/README.md)
- Web API auth & endpoints → [`packages/web/api/README.md`](./packages/web/api/README.md)
- MCP connectors → [`packages/brain-mcp/README.md`](./packages/brain-mcp/README.md) & [`connectors/`](./packages/brain-mcp/connectors)
- Extension build & store → [`packages/browser-extension/README.md`](./packages/browser-extension/README.md) & [`PUBLISHING.md`](./packages/browser-extension/PUBLISHING.md)
- Brain config reference → [`config.example.yaml`](./config.example.yaml)
