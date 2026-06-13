# isitme — web

A local-run web product for your **portable online brain**. Two processes plus
the Core Brain:

| Service     | Port | Path                      | What it does                                  |
| ----------- | ---- | ------------------------- | --------------------------------------------- |
| Core Brain  | 8077 | `packages/brain-core`     | Knowledge graph + memory (local-first)        |
| Web API/BFF | 5050 | `packages/web/api`        | Google OAuth, API keys, MCP config, brain proxy |
| Frontend    | 4000 | `packages/web/frontend`   | Landing page + authenticated dashboard        |

> Ports **4000** and **5050** are mandatory — the Google OAuth client pins
> `javascript_origins=[http://localhost:4000]` and
> `redirect_uris=[http://localhost:5050/auth/google/callback]`.

---

## Prerequisites

- **Python 3.11+** and **Node 18+**
- A repo-root **`.env`** (gitignored) containing:
  - `OAUTH_CLIENT_JSON` — the Google OAuth *web* client JSON
  - `OPENAI_API_KEY` — optional, enriches "Ask your brain"
- The brain can run with zero config. To customize it, copy the example config:

```bash
# from the repo root
cp config.example.yaml config.yaml   # optional; brain runs fine without it
```

`.env` is already gitignored — never commit it.

---

## One-time setup

From `packages/web/`:

```bash
# 1) Python venv with the Web API + Core Brain dependencies
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e ./api "openai>=1.20" \
    "numpy>=1.26" "pyyaml>=6.0" "cryptography>=42.0"

# 2) Frontend + the dev orchestrator deps
npm install                 # installs `concurrently` here
npm run install:web         # installs the frontend (packages/web/frontend)
```

> The Core Brain is run via `PYTHONPATH` (no separate install needed). Its
> runtime deps (numpy/pyyaml/cryptography) are installed into the same venv above.

---

## Run everything (all three services)

```bash
# from packages/web/
./dev.sh
# or, equivalently:
npm run dev
```

Then open **http://localhost:4000** and click **Sign in with Google**.

### Run services individually

```bash
# Core Brain  (:8077)
PYTHONPATH=../brain-core/src .venv/bin/python -m brain_core serve --port 8077

# Web API     (:5050)
.venv/bin/python -m web_api --port 5050

# Frontend    (:4000)
npm --prefix frontend run dev
```

---

## Build & verify

```bash
# Frontend production build (tsc + vite)
npm run build:web

# Web API smoke tests (boots app, checks auth guards)
npm run test:api

# Seed a few events so the 3D graph isn't empty (brain must be running):
curl -s -X POST http://127.0.0.1:8077/v1/ingest \
  -H 'content-type: application/json' \
  -d '{"client":"seed","events":[
        {"type":"search","data":{"query":"vector databases"},"url":"https://google.com/search"},
        {"type":"visit","title":"pgvector","url":"https://github.com/pgvector/pgvector"},
        {"type":"llm_chat","content":"compare pgvector vs qdrant","data":{"model":"gpt-4o"}}
      ]}'
```

---

## Manual step you must do in Google Cloud

The OAuth client is already created (see `.env`). For sign-in to succeed you must:

1. In **Google Cloud Console → APIs & Services → OAuth consent screen**, ensure
   the consent screen is configured and **add your Google account as a Test user**
   (while the app is in "Testing").
2. Confirm the client's **Authorized redirect URI** is exactly
   `http://localhost:5050/auth/google/callback` and **Authorized JavaScript origin**
   is `http://localhost:4000` (these already match `.env`).

If you see `redirect_uri_mismatch`, the ports above don't match — keep 4000/5050.

---

## Endpoints (Web API)

- `GET  /auth/google/login` → redirect to Google
- `GET  /auth/google/callback` → sets session, redirects to `/dashboard`
- `GET  /auth/me`, `POST /auth/logout`
- `POST /api/keys`, `GET /api/keys`, `DELETE /api/keys/{id}` *(session only)*
- `GET  /api/keys/validate` *(`X-API-Key` only)* → `{valid, user}`
- `GET  /api/mcp-config` (`?mint=true` to embed a fresh key once)
- `GET  /api/graph`, `GET /api/stats`, `GET /api/profile`, `POST /api/ask`
- `POST /api/ingest`, `POST /api/log`, `POST /api/recall`, `POST /api/search`
- `GET  /api/extension/usage`
- `GET  /healthz`

### Auth contract

Every `/api/*` data endpoint accepts **either** a browser **session cookie**
**or** a header **`X-API-Key: <plaintext>`** (so MCP and the browser extension
can use them). Keys are stored only as a SHA-256 hash (never plaintext); the
hash is matched, the user resolved, and `last_used` updated on each call. CORS
allows `http://localhost:4000` (credentials) and `chrome-extension://*`, and
permits the `X-API-Key` header. Full table + shapes: `packages/web/api/README.md`.

The dashboard's 3D graph is sourced from the brain's read-only
`GET /v1/graph` (added to `brain-core`), reshaped for `react-force-graph`.

### Storage (SQLite default, MongoDB opt-in)

Both the Core Brain and the Web API run on SQLite/numpy with **zero services**.
To opt into MongoDB: `docker compose up -d mongodb`, then set the brain's
`storage.*_backend: mongodb` (config/env) and the web API's `WEB_MONGO_URI`.
Details: `packages/brain-core/README.md` and `packages/web/api/README.md`.
