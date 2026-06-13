# isitme — Validation & Skills

Two parts:

- **[Part A — Validation](#part-a--validation):** how to verify the system works
  end-to-end (test suites, a manual checklist, privacy/redaction checks, OAuth
  security checks, and troubleshooting).
- **[Part B — Skills](#part-b--skills):** the brain's capabilities exposed to
  LLMs as MCP tools, when/how an agent should use each, and how to extend the
  brain with new event types, relations, embeddings/backends, and tools.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the model and
[DEPLOYMENT.md](./DEPLOYMENT.md) for setup.

---

## Table of contents

- [Part A — Validation](#part-a--validation)
  - [A1. Test suites per package](#a1-test-suites-per-package)
  - [A2. Manual end-to-end checklist](#a2-manual-end-to-end-checklist)
  - [A3. Privacy & redaction validation](#a3-privacy--redaction-validation)
  - [A4. OAuth / auth security validation](#a4-oauth--auth-security-validation)
  - [A5. Troubleshooting](#a5-troubleshooting)
- [Part B — Skills](#part-b--skills)
  - [B1. MCP tools (the brain's skills)](#b1-mcp-tools-the-brains-skills)
  - [B2. A recommended agent flow](#b2-a-recommended-agent-flow)
  - [B3. Extending the brain](#b3-extending-the-brain)

---

# Part A — Validation

## A1. Test suites per package

Each package has its own suite. Run them from the package directory (Python
packages use `pytest` with `asyncio_mode = "auto"`).

### brain-core (pytest)

```bash
pip install -e "packages/brain-core[dev]"
pytest packages/brain-core
# or: cd packages/brain-core && python -m pytest
```

- `tests/test_roundtrip.py` — the core contract: ingest → graph update → recall
  round-trip; redaction happens before storage; capture filters drop unwanted
  events; edge weights decay over time. (`conftest.py` builds a fully-local
  `Brain` rooted at a temp dir.)
- `tests/test_mongo_storage.py` — the MongoDB stores (uses `mongomock-motor`, so
  no real Mongo needed).

### web / api (pytest)

```bash
cd packages/web
.venv/bin/python -m pytest api/tests -q     # or: npm run test:api
```

- `tests/test_auth.py` — the shared auth contract: a valid `X-API-Key` is
  accepted, invalid/missing/revoked is rejected, data endpoints reach the brain
  proxy rather than 401 (plus the `MongoWebStore` key path).
- `tests/test_smoke.py` — boots the app and checks the auth guards.

### brain-mcp (pytest)

```bash
cd packages/brain-mcp
.venv/bin/python -m pytest
.venv/bin/ruff check .
```

- `tests/test_server.py` — the server constructs and all six tools register with
  schemas; config fails fast without credentials.
- `tests/test_tools_http.py` — mocks the HTTP layer (`respx`) and asserts each
  tool hits the right Web-API endpoint with the auth header.

### browser-extension (build / typecheck)

```bash
cd packages/browser-extension
npm install
npm run typecheck     # tsc --noEmit (strict)
npm run build         # typecheck + esbuild bundle -> dist/
```

A clean `npm run build` (strict typecheck + bundle) is the extension's gate;
verify `dist/` contains `manifest.json`, `background.js`, `content.js`,
`popup.*`, `options.*`, and `icons/`.

### Lint (all Python packages)

```bash
ruff check packages/brain-core packages/web/api packages/brain-mcp
```

---

## A2. Manual end-to-end checklist

Boot all three services (`cd packages/web && ./dev.sh`) and walk the full path:

1. **Health.**
   `curl -s http://127.0.0.1:8077/healthz` → `{"status":"ok"}`.
   `curl -s http://127.0.0.1:5050/healthz` → shows `oauth_configured` and
   `brain_reachable: true`.
2. **Sign in.** Open `http://localhost:4000`, click **Sign in with Google**,
   complete consent → you land on `/dashboard` (a session cookie is set).
3. **Capture events.** Either:
   - load the extension (`dist/`), set API base `http://127.0.0.1:5050`, sign in,
     browse a few pages / run a search; **or**
   - seed directly (brain): the `curl` in [DEPLOYMENT.md §5](./DEPLOYMENT.md#5-run-each-service-individually).
4. **See the 3D graph.** Reload the dashboard — the `react-force-graph-3d`
   visualization should show typed, colored nodes (user/domain/url/topic/…),
   sourced from `GET /api/graph` → brain `GET /v1/graph`.
5. **Check stats/profile.**
   `curl -s http://127.0.0.1:8077/v1/stats` → non-zero `events`, `nodes`,
   `edges`, `memories`.
   `GET /v1/profile` → interests/top_domains/behavior_types populated.
6. **Query via MCP.** With the MCP server configured in your LLM host
   ([DEPLOYMENT.md §7](./DEPLOYMENT.md#7-deploying-the-mcp-server)), ask the
   agent to call `get_stats`, then `get_user_profile`, then `recall_context`
   / `ask_brain` about something you just captured — answers should reflect the
   seeded/captured data.
7. **Round-trip a write.** Have the agent call `log_interaction(type="opinion",
   content="…")`; confirm `events`/`nodes` increment via `get_stats`.

---

## A3. Privacy & redaction validation

Redaction runs **twice** (client-side in the extension, server-side in the
brain) — verify both.

**What gets scrubbed** (server `RedactionEngine`, `redaction/engine.py`):
built-in detector categories `passwords`, `banking`, `health`, `secrets`
(API keys, tokens, private keys), and `pii` (emails, phones, credit-card-ish,
SSNs), plus user `custom_patterns`. Matches in `title`, `content`, `url`, and
string values in `data` are replaced with `replacement` (default `[REDACTED]`).

**Allow/deny semantics to verify:**

- `deny_sites` → the event is **dropped entirely** (never stored). Confirm via
  the ingest summary `dropped` count and that no node appears for that domain.
- `content_blocklist_sites` → content/title scrubbed to `null`, metadata kept.
- `allow_sites` → when non-empty, **only** those domains are captured.

**Quick test:**

```bash
curl -s -X POST http://127.0.0.1:8077/v1/ingest -H 'content-type: application/json' -d '{
  "client":"test","events":[
    {"type":"visit","url":"https://example.com","title":"hi",
     "content":"my email is a@b.com and key sk-ABCDEFGHIJKLMNOP123456"}
  ]}'
# response includes "redactions": <n> > 0; stored content shows [REDACTED]
```

**Client-side** (`common/redaction.ts`): the extension background worker scrubs
credit cards (Luhn-validated), SSNs, OpenAI/Anthropic/Stripe/AWS/GitHub/Google
keys, JWTs, bearer tokens, isitme keys, and sensitive `key=value` pairs **before**
anything is queued or sent; password input values are never read. Validate by
inspecting the queued payload (or the brain's stored event) for a page
containing a fake secret — it should already be masked on arrival.

**Defaults that matter:** LLM-chat capture and page-content capture are **off**
by default in the extension; redaction is **on**; banking/auth hosts are denied
out of the box.

---

## A4. OAuth / auth security validation

OAuth is the primary, documented mechanism (see
[ARCHITECTURE.md §7](./ARCHITECTURE.md#7-auth--data-flow)). Verify:

- **Unauthenticated requests are rejected.** `curl -s -o /dev/null -w '%{http_code}'
  http://127.0.0.1:5050/api/stats` → `401` with no cookie/credential.
- **Bearer/identity is required and verified.** A request carrying
  `Authorization: Bearer <google token>` resolves to the correct user; a forged
  or expired token is rejected (`401/403`). The Web API verifies the token with
  Google and resolves the user before proxying.
- **Session cookie is signed & scoped.** The cookie is signed with the server
  secret (`./.brain/web/session_secret.key`, persisted & `chmod 600`); CORS
  allows only `http://localhost:4000` (credentialed) and `chrome-extension://*`.
- **State/nonce on the extension flow.** `background/auth.ts` generates and
  checks `state` (aborts on mismatch) and validates the userinfo `sub`.
- **No secrets in the client.** The extension uses the public client ID with the
  implicit flow — it never holds the OAuth **client secret**.
- **Legacy API keys** (if still used) are stored only as SHA-256 hashes;
  `GET /api/keys/validate` accepts a valid key and `401`s an invalid/revoked one;
  revocation takes effect immediately.

---

## A5. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `redirect_uri_mismatch` (Google) | The redirect URI/port sent doesn't exactly match a registered one | Keep ports **4000/5050**; register the exact callback (`http://localhost:5050/auth/google/callback`), the extension `https://<EXTENSION_ID>.chromiumapp.org/`, and any MCP loopback URI in the OAuth client ([DEPLOYMENT.md §9](./DEPLOYMENT.md#9-google-cloud-console-setup)) |
| `access_denied` at consent | Account isn't a Test user (consent screen in Testing) | Add the account under OAuth consent screen → Test users, or publish the app |
| `503 Google OAuth is not configured` | `OAUTH_CLIENT_JSON` missing/malformed | Add it to the repo-root `.env`; check the JSON is valid |
| **Connection refused** / brain unreachable / `502 Core Brain unavailable` | A service isn't running | Start the missing one (brain `:8077`, Web API `:5050`); the MCP tools and Web API report this clearly |
| MCP tools error "API key rejected" / unreachable | Legacy key invalid/revoked, or Web API down | Re-run `brain-mcp login` (OAuth), or regenerate a key and update the connector; ensure the Web API is up |
| **npm `401 Unauthorized`** on install | A private registry is configured | Install from the package dir so the project `.npmrc` (public registry) applies; remove conflicting global `~/.npmrc` ([DEPLOYMENT.md §6](./DEPLOYMENT.md#npm-private-registry-gotcha)) |
| Empty 3D graph | No events captured yet | Seed events or browse with the extension; confirm `GET /v1/stats` is non-zero |
| `NotImplementedError: graph_backend=… not bundled` | Selected a roadmap backend (neo4j/kuzu/qdrant/pgvector) | Use a bundled backend (`sqlite`/`mongodb`/`postgres` for graph/events; `numpy`/`chroma`/`mongodb` for vectors) or implement the adapter |
| Sign-in works but `/api/ask` returns a templated answer | `OPENAI_API_KEY` not set | Set it in `.env` to enable OpenAI synthesis (`synthesized_by: "openai"`) |

---

# Part B — Skills

The brain exposes its capabilities to any MCP-capable LLM host as **six tools**
(`packages/brain-mcp/src/brain_mcp/server.py`). Each is a thin, typed call into
the Web API, which authenticates and proxies to the Core Brain. Think of these
as the agent's "skills" for grounding itself in *this specific user*.

## B1. MCP tools (the brain's skills)

| Tool | Web API endpoint | Returns | Use it when… |
| --- | --- | --- | --- |
| `get_user_profile()` | `GET /api/profile` | interests, top domains, behavior types, decision patterns, recurring opinions, summary | **Early**, to personalize: understand the user's mindset/habits before answering. |
| `recall_context(query, k=5)` | `POST /api/recall` | top-k semantic memories **+ graph context** (related topics & their strongest neighbors) | You need the **tightest** memories relevant to the current task, grounded in structure. |
| `search_memory(query, k=8)` | `POST /api/search` | top-k semantic hits `(id, score, text, metadata)` | **Broader exploration** of what the user has seen/done/written — wider net than recall. |
| `ask_brain(question, k=6)` | `POST /api/ask` | a synthesized answer + `sources` + `graph_context` + `profile_summary` | You want a **direct answer** about the user rather than raw memories. |
| `log_interaction(type, content?, url?, title?, data?)` | `POST /api/log` | ingest summary | **Write back**: record a stated opinion (`type="opinion"`) or a notable exchange (`type="llm_chat"`) so the brain improves. |
| `get_stats()` | `GET /api/stats` | counters (events, nodes, edges, memories) + mode + embedding provider | **Gauge coverage** before relying on recall/search; confirm the brain is reachable. |

Notes:

- `log_interaction`'s `type` must be one of `visit`, `click`, `dwell`, `link`,
  `search`, `llm_chat`, `content_create`, `opinion` (invalid types raise a clear
  error). Events are tagged `source: "mcp"`.
- `k` is clamped to `1..50`. Recall/ask fuse vector search with graph traversal;
  `search_memory` is vector-only.
- If a tool reports the brain is unreachable or the credential is invalid, tell
  the user how to fix it (start the Web API; re-`login`) rather than guessing —
  this guidance is baked into the server's instructions.

## B2. A recommended agent flow

```
get_stats()            → is the brain populated & reachable?
   │ yes
get_user_profile()     → who is this user? (interests, archetype, opinions)
   │
recall_context(task)   → tightest memories + related topics for THIS task
   │  (or search_memory for broad exploration; ask_brain for a direct answer)
   ▼
…answer, grounded in brain facts over assumptions…
   │
log_interaction(opinion/llm_chat)   → write notable outcomes back
```

## B3. Extending the brain

The codebase is built around clean seams — most extensions touch one or two
files. (See [ARCHITECTURE.md](./ARCHITECTURE.md) for context.)

### Add a new event type

1. Add a value to `EventType` (`brain_core/models/events.py`) and to the
   `categories` defaults in `config.py` (`CaptureSettings`).
2. Handle it in `InsightEngine.process_events` (`engine/insight.py`): upsert the
   relevant nodes and `observe_edge(...)` relations (reuse `_attach_topics` for
   text). Ensure `text_for_memory()` returns the text you want embedded.
3. Mirror the type in the MCP tool's `_EVENT_TYPES` (`brain_mcp/server.py`) if it
   should be loggable, and emit it from the extension if it's browser-captured.

### Add a new graph relation

1. Add a value to `RelationType` (`models/graph.py`).
2. Create edges with it via `observe_edge(src, dst, RelationType.YOURS, weight,
   at)` in the insight engine. Decay/reinforce and `(src,dst,relation)` dedup are
   automatic — no store changes needed (both SQLite and Mongo are generic over
   relation strings).

### Add a new embedding provider or storage backend

- **Embeddings:** implement the `EmbeddingProvider` ABC
  (`embeddings/base.py`: `dim` + `embed`) and add a branch in
  `factory.build_embeddings`; expose it in `EmbeddingSettings.provider`.
- **Storage:** implement the matching ABC in `storage/base.py`
  (`EventStore` / `GraphStore` / `VectorStore` / `OutboxStore`) and add a branch
  in the corresponding `factory.build_*`. For graph/vector backends, reuse the
  decay math in `engine/decay.py` so semantics match. Add the backend name to the
  `Literal[...]` in `StorageSettings`. The Atlas `$vectorSearch` snippet in
  `storage/mongo/vector_store.py` is a template for a native-ANN `query()`.
- Nothing else changes: the brain depends only on the ABCs.

### Add a new MCP tool

1. In `brain_mcp/client.py`, add a method that calls the relevant Web API
   endpoint (add the endpoint to the Web API if it doesn't exist, wiring it
   through `BrainClient` → Core Brain).
2. In `brain_mcp/server.py`, register an `@mcp.tool(...)` with a clear `title`,
   `description` (when/how an agent should use it), and typed `Annotated` params.
3. Add a test in `tests/test_tools_http.py` (mock the HTTP call) and confirm it
   appears in `tests/test_server.py`'s registered-tools assertion.

---

## Cross-references

- System architecture → [ARCHITECTURE.md](./ARCHITECTURE.md)
- Operator guide → [DEPLOYMENT.md](./DEPLOYMENT.md)
- MCP tools & connectors → [`packages/brain-mcp/README.md`](./packages/brain-mcp/README.md)
- Web API auth & endpoints → [`packages/web/api/README.md`](./packages/web/api/README.md)
- Extension privacy & permissions → [`packages/browser-extension/README.md`](./packages/browser-extension/README.md)
- Brain internals → [`packages/brain-core/README.md`](./packages/brain-core/README.md)
