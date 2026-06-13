# web-api

The isitme **Web API / BFF** (FastAPI, port **5050**).

It provides Google OAuth login, signed session cookies for the frontend on
`http://localhost:4000`, API-key management (the keys the browser extension /
MCP server use), an MCP-config generator, and a proxy over the Core Brain
(`http://127.0.0.1:8077`) for the dashboard, MCP and the extension.

See `packages/web/README.md` for run instructions.

## Authentication contract (shared with MCP + extension)

A request is authenticated if it presents **either**:

- a valid **browser session cookie** (set after Google OAuth), **or**
- a header **`X-API-Key: <plaintext>`**.

The plaintext key is SHA-256 hashed and looked up among the stored,
**non-revoked** hashes; the owning user is resolved and the key's `last_used`
is updated. **Plaintext keys are never stored or logged** — only the hash, a
short prefix, label, owner, `created_at`, `last_used` and `revoked` flag.

The reusable FastAPI guards live in `src/web_api/auth.py`:

- `require_user`  — session cookie only (used for API-key management).
- `require_auth`  — session **or** `X-API-Key` (the brain-proxy data endpoints).
- `require_api_key` — a valid `X-API-Key` specifically (`/api/keys/validate`).

### Endpoints

Auth column: **S** = session cookie, **K** = `X-API-Key`.

| Method & path            | Auth | Body / query                       | Proxies to brain    |
| ------------------------ | ---- | ---------------------------------- | ------------------- |
| `POST /api/ingest`       | S+K  | `{client, events: [...]}`          | `/v1/ingest`        |
| `POST /api/log`          | S+K  | a single raw event object          | `/v1/log`           |
| `POST /api/recall`       | S+K  | `{query, k}`                       | `/v1/recall`        |
| `POST /api/search`       | S+K  | `{query, k}`                       | `/v1/search_memory` |
| `GET  /api/profile`      | S+K  | —                                  | `/v1/profile`       |
| `POST /api/ask`          | S+K  | `{question, k}`                    | `/v1/ask`           |
| `GET  /api/graph`        | S+K  | `?node_limit&edge_limit`           | `/v1/graph`         |
| `GET  /api/stats`        | S+K  | —                                  | `/v1/stats`         |
| `GET  /api/extension/usage` | S+K | —                               | `/v1/stats` (+graph)|
| `GET  /api/keys/validate`| K    | (header only)                      | —                   |
| `POST /api/keys`         | S    | `{name}`                           | —                   |
| `GET  /api/keys`         | S    | —                                  | —                   |
| `DELETE /api/keys/{id}`  | S    | —                                  | —                   |
| `GET  /api/mcp-config`   | S    | `?mint&name&key`                   | —                   |

`GET /api/keys/validate` returns `{ "valid": true, "user": { id, email, name,
picture } }` for a valid key (HTTP 401 otherwise). Clients use it to verify a
key before use.

Example (non-browser client):

```bash
curl -s http://127.0.0.1:5050/api/keys/validate -H 'X-API-Key: isme_...'
curl -s -X POST http://127.0.0.1:5050/api/ingest \
  -H 'X-API-Key: isme_...' -H 'content-type: application/json' \
  -d '{"client":"extension","events":[{"type":"visit","url":"https://x.com","title":"x"}]}'
```

### CORS

Credentialed CORS allows the frontend origin (`http://localhost:4000`) and the
browser-extension origin pattern (`chrome-extension://*`); the `X-API-Key`
header is allowed so the extension/MCP can call `/api/ingest`,
`/api/keys/validate` and the other `/api/*` endpoints.

## Persistence (SQLite default, MongoDB opt-in)

Users, API keys and usage are stored in SQLite by default (`./.brain/web/web.db`),
zero setup. To use MongoDB instead, set:

```bash
WEB_MONGO_URI=mongodb://localhost:27017   # enables Mongo when set
WEB_MONGO_DB=isitme                       # default: isitme
```

Start Mongo with `docker compose up -d mongodb` (repo root). Collections:
`users`, `api_keys` (hash + prefix + label + owner + timestamps + revoked only)
and `usage`. Unset `WEB_MONGO_URI` → SQLite (still runs with zero services).
