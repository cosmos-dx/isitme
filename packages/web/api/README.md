# web-api

The isitme **Web API / BFF** (FastAPI, port **5050**).

It provides Google OAuth login, signed session cookies for the frontend on
`http://localhost:4000`, API-key management (the keys the browser extension /
MCP server use), an MCP-config generator, and a proxy over the Core Brain
(`http://127.0.0.1:8077`) for the dashboard, MCP and the extension.

See `packages/web/README.md` for run instructions.

## Authentication contract (shared with MCP + extension)

A request to `/api/*` is authenticated if it presents **any** of:

1. a valid **browser session cookie** (set after Google OAuth) — the dashboard, or
2. a header **`Authorization: Bearer <google_oauth_token>`** — **the documented
   path for the MCP server and the browser extension**, or
3. a header **`X-API-Key: <plaintext>`** — **legacy/optional**, kept working but
   no longer recommended for new clients.

### Google Bearer tokens (the primary contract)

The token is a **Google OAuth token** for *our* OAuth client:

- An **OIDC `id_token`** (preferred) — a signed JWT. We verify the signature,
  issuer and expiry, and that its `aud` equals our `client_id`, **offline**
  against Google's published signing keys
  (`google.oauth2.id_token.verify_oauth2_token`).
- A Google **`access_token`** — opaque. We verify it against Google's
  `tokeninfo` endpoint, confirm it was minted for our `client_id`
  (`aud`/`azp` — a confused-deputy guard), then enrich name/picture from
  `userinfo`.

We **never trust unverified claims**: a token is honored only after Google (or
its signing keys) vouches for it *and* the audience is ours. The verified
`sub`/`email` then **resolves-or-creates** the user (updating `last_login`).
Verified tokens are cached (per token, until shortly before expiry) so the hot
path doesn't call Google on every request. Implementation:
`src/web_api/google_auth.py`.

`GET /auth/oauth-config` returns the **non-secret** `client_id` (plus auth/token
URIs, scopes and any registered loopback redirect URIs) so local clients can
initiate OAuth without hardcoding it. The client **secret is never served**.

`GET /auth/me` resolves the caller from a session cookie **or** a Bearer token
(or legacy key) — clients use it to confirm who their token authenticates as.

### Legacy `X-API-Key`

The plaintext key is SHA-256 hashed and looked up among the stored,
**non-revoked** hashes; the owning user is resolved and the key's `last_used`
is updated. **Plaintext keys are never stored or logged** — only the hash, a
short prefix, label, owner, `created_at`, `last_used` and `revoked` flag.

The reusable FastAPI guards live in `src/web_api/auth.py`:

- `require_user`  — session cookie only (used for API-key management).
- `require_auth`  — session **or** Google Bearer **or** `X-API-Key` (brain-proxy
  data endpoints).
- `require_api_key` — a valid `X-API-Key` specifically (`/api/keys/validate`).

### Endpoints

Auth column: **S** = session cookie, **B** = `Authorization: Bearer <google token>`,
**K** = legacy `X-API-Key`.

| Method & path            | Auth  | Body / query                      | Proxies to brain    |
| ------------------------ | ----- | --------------------------------- | ------------------- |
| `POST /api/ingest`       | S+B+K | `{client, events: [...]}`         | `/v1/ingest`        |
| `POST /api/log`          | S+B+K | a single raw event object         | `/v1/log`           |
| `POST /api/recall`       | S+B+K | `{query, k}`                      | `/v1/recall`        |
| `POST /api/search`       | S+B+K | `{query, k}`                      | `/v1/search_memory` |
| `GET  /api/profile`      | S+B+K | —                                 | `/v1/profile`       |
| `POST /api/ask`          | S+B+K | `{question, k}`                   | `/v1/ask`           |
| `GET  /api/graph`        | S+B+K | `?node_limit&edge_limit`          | `/v1/graph`         |
| `GET  /api/stats`        | S+B+K | —                                 | `/v1/stats`         |
| `GET  /api/extension/usage` | S+B+K | —                             | `/v1/stats` (+graph)|
| `GET  /auth/me`          | S+B+K | (header/cookie only)              | —                   |
| `GET  /auth/oauth-config`| —     | (public)                          | —                   |
| `GET  /api/keys/validate`| K     | (header only)                     | —                   |
| `POST /api/keys`         | S     | `{name}`                          | —                   |
| `GET  /api/keys`         | S     | —                                 | —                   |
| `DELETE /api/keys/{id}`  | S     | —                                 | —                   |
| `GET  /api/mcp-config`   | S     | `?mint&name&key`                  | —                   |

`GET /api/keys/validate` returns `{ "valid": true, "user": { id, email, name,
picture } }` for a valid key (HTTP 401 otherwise). `GET /auth/me` returns
`{ "authenticated": true|false, "user": {...}? }` for any accepted credential.

Example (non-browser client — the documented Bearer path):

```bash
# Confirm who a Google token authenticates as:
curl -s http://127.0.0.1:5050/auth/me -H 'Authorization: Bearer <google_id_token>'
# Ingest events with a Google token:
curl -s -X POST http://127.0.0.1:5050/api/ingest \
  -H 'Authorization: Bearer <google_id_token>' -H 'content-type: application/json' \
  -d '{"client":"extension","events":[{"type":"visit","url":"https://x.com","title":"x"}]}'

# Legacy key path (still works):
curl -s http://127.0.0.1:5050/api/keys/validate -H 'X-API-Key: isme_...'
```

### CORS

Credentialed CORS allows the frontend origin (`http://localhost:4000`) and the
browser-extension origin pattern (`chrome-extension://*`); the `Authorization`
and `X-API-Key` headers are allowed so the extension/MCP can call `/api/ingest`
and the other `/api/*` endpoints with a Google Bearer token (or a legacy key).

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
