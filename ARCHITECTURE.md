# isitme — Architecture

`isitme` is a personal, **local-first "central brain."** It captures how you
behave online — across browsers and across LLMs — models that behavior as a
weighted, time-decaying knowledge graph plus semantic memory, and exposes the
result to *any* LLM (via MCP) and to a browser dashboard. The premise:

> **Switch any browser or any LLM — your brain comes back.**

Collectors and consumers are deliberately thin clients. All cognition lives in
one stateful service (the **Core Brain**); everything else is a cable into it.

---

## Table of contents

1. [The big picture](#1-the-big-picture)
2. [Component diagram](#2-component-diagram)
3. [The data model](#3-the-data-model)
   - [Raw event log](#31-raw-event-log)
   - [Knowledge graph: nodes, edges, traces](#32-knowledge-graph-nodes-edges-traces)
   - [Time decay and re-strengthening](#33-time-decay-and-re-strengthening)
   - [Derived profile / insights](#34-derived-profile--insights)
4. [How the graph is built (ingest → graph → memory)](#4-how-the-graph-is-built)
5. [Recall & ask: RAG over graph + vector](#5-recall--ask-rag-over-graph--vector)
6. [Fast traversal & scalability](#6-fast-traversal--scalability)
7. [Auth & data flow](#7-auth--data-flow)
8. [Privacy & redaction](#8-privacy--redaction)
9. [Cross-references](#9-cross-references)

---

## 1. The big picture

There are three roles in the system:

| Role | Component(s) | Stateful? | Job |
| --- | --- | --- | --- |
| **Collectors** | Browser extension (MV3); `log_interaction` from LLMs | No | Capture signals of online behavior and push them in. |
| **The brain** | `packages/brain-core` (the **Core Brain**) | **Yes** | Store events, build the knowledge graph + semantic memory, derive a profile, answer recall/RAG queries. |
| **Consumers** | `packages/brain-mcp` (MCP server), `packages/web` dashboard | No | Read the brain to ground an LLM or visualize you. |

The Core Brain is the **only stateful component**. Collectors and consumers
never hold cognition — they speak HTTP/JSON to the brain (in practice via the
Web API/BFF). This is what makes the brain portable: replace Chrome with Arc,
or ChatGPT with Claude, and the same brain keeps answering.

A second key idea is **swappable backends behind ABCs**. The brain depends only
on storage interfaces (`EventStore`, `GraphStore`, `VectorStore`, `OutboxStore`)
and an `EmbeddingProvider`. The default stack is fully local and needs zero
network or API keys (SQLite + in‑process numpy vectors + a hashing embedder);
each tier can be swapped for a production backend via config alone.

---

## 2. Component diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│ COLLECTORS                                                                 │
│                                                                            │
│  Browser extension (MV3)         LLM hosts (Cursor / Claude / …)           │
│   content scripts → bg worker        │                                     │
│   (redact + policy gate)             │ log_interaction (opinions/chats)    │
│        │  POST /api/ingest           │                                     │
└────────┼─────────────────────────────┼────────────────────────────────────┘
         │ X-API-Key / Bearer          │ MCP tools (stdio / http)
         ▼                             ▼
   ┌───────────────────────────────────────────────┐        ┌──────────────┐
   │ packages/web  —  Web API / BFF  (FastAPI :5050) │◀──────▶│ brain-mcp     │
   │  • Google OAuth login → session cookie          │  MCP   │ (MCP server)  │
   │  • API-key mgmt + OAuth bearer verification     │ tools  │ thin HTTP     │
   │  • read-only proxy over the Core Brain          │        │ client        │
   │  • optional OpenAI answer synthesis             │        └──────────────┘
   └───────────────┬─────────────────────────────────┘
                   │ HTTP /v1/*               ▲
                   ▼                          │ React + react-force-graph-3d
   ┌─────────────────────────────────────┐   │  (dashboard, Vite :4000)
   │ packages/brain-core — CORE BRAIN     │   └───────────────────────────────
   │ (FastAPI :8077, the ONLY stateful)   │
   │                                      │
   │  Redaction ─▶ Insight engine ─▶ ...  │
   │   EventStore   GraphStore   VectorStore   OutboxStore   Embeddings        │
   │      │            │             │            │                            │
   │   sqlite/       sqlite/       numpy/       sqlite ─▶ (encrypted) cloud sync│
   │   postgres/     neo4j/        chroma/                                      │
   │   mongodb       mongodb       qdrant/pgvector/mongodb                      │
   └──────────────────────────────────────────────────────────────────────────┘
```

Ports are fixed by design (see [DEPLOYMENT.md](./DEPLOYMENT.md)):
`4000` frontend, `5050` Web API, `8077` Core Brain.

Per-package details:
[`brain-core`](./packages/brain-core/README.md),
[`web`](./packages/web/README.md),
[`web/api`](./packages/web/api/README.md),
[`brain-mcp`](./packages/brain-mcp/README.md),
[`browser-extension`](./packages/browser-extension/README.md).

---

## 3. The data model

The brain has three layers, each derived from the one before it:

```
raw event log  ──▶  knowledge graph  ──▶  derived profile / insights
(append-only)       (typed nodes +         (interests, behavior types,
                     weighted/decaying       decision patterns, opinions)
                     edges + traces)
        │
        └──▶  semantic memory (text + embedding vectors)
```

### 3.1 Raw event log

Every captured signal is a single `RawEvent`
(`packages/brain-core/src/brain_core/models/events.py`) — a typed envelope plus
a flexible `data` payload, kept append-only:

```python
class EventType(str, Enum):
    VISIT = "visit"; CLICK = "click"; DWELL = "dwell"; LINK = "link"
    SEARCH = "search"; LLM_CHAT = "llm_chat"
    CONTENT_CREATE = "content_create"; OPINION = "opinion"

class RawEvent(BaseModel):
    id: str; type: EventType; timestamp: datetime
    source: str = "unknown"          # "browser-extension", "mcp", "api", …
    session_id: str | None
    url: str | None; title: str | None; content: str | None
    data: dict[str, Any]             # type-specific extras
```

Two helpers keep downstream code clean: `event.domain` (normalized netloc, `www.`
stripped) and `event.text_for_memory()` (the title + content + `data["query"]`
text that gets embedded). Collectors POST a `EventBatch` (`{client, events:[…]}`).

### 3.2 Knowledge graph: nodes, edges, traces

The brain is a **directed multigraph** of typed entities
(`packages/brain-core/src/brain_core/models/graph.py`):

**Node types** (`NodeType`):

| Type | Meaning | Dedup key (`key`) |
| --- | --- | --- |
| `user` | You (the singleton `"me"`) | `"me"` |
| `domain` | A site | normalized domain |
| `url` | A page | the URL |
| `topic` | An extracted keyword/topic | lowercased token |
| `query` | A search query | lowercased query |
| `llm` | A model you chatted with | model name |
| `opinion` | A stated belief/preference | md5 of the text |
| `document` | Something you created | url or md5 of content |
| `person` | A mentioned person/entity | — |

**Relation types** (`RelationType`) carried by edges:

| Relation | Typical direction |
| --- | --- |
| `visited` | user → domain / url |
| `contains` | domain → url |
| `searched` | user → query |
| `led_to` | query/url → url (navigation / link trail) |
| `about` | url/query/chat/doc/opinion → topic |
| `interested_in` | user → topic |
| `chatted_with` | user → llm |
| `holds` | user → opinion |
| `created` | user → document |
| `mentions` | any → entity/person |

A **`Node`** carries a cumulative `weight` (sum of decayed observations), a
`label`, free-form `attributes`, and timestamps. Crucially it is deduped on
`(type, key)` so re-seeing the same topic/domain/url updates one node.

An **`Edge`** carries a *raw* `weight` paired with a `last_seen` timestamp, plus
an `effective_weight` field that the store populates on read (the decayed value
"as of now"). Edges are deduped on `(src, dst, relation)`.

A **`Trace`** is a browsing session reconstructed as an ordered path of node ids
(`session_id`, `node_ids`, `started_at`, `ended_at`) — the literal trail you
followed.

### 3.3 Time decay and re-strengthening

Edge/node importance is **recency-biased** via exponential decay with a
configurable half-life (`graph.edge_half_life_days`, default 30). The math lives
in `packages/brain-core/src/brain_core/engine/decay.py`:

```python
def decay_factor(elapsed_days, half_life_days):
    return 0.5 ** (elapsed_days / half_life_days)   # 1.0 if no/zero elapsed

def effective_weight(weight, last_seen, now, half_life_days):
    elapsed = (now - last_seen).total_seconds() / 86400.0
    return weight * decay_factor(elapsed, half_life_days)

def reinforce(prev_weight, last_seen, delta, now, half_life_days):
    # decay the prior value to *now*, then add the new increment
    return effective_weight(prev_weight, last_seen, now, half_life_days) + delta
```

The stored raw `weight` is the **effective weight at the moment it was last
observed**. Reading it later decays it to "now"; observing the edge again
(`observe_edge`) decays the prior value to the observation time and *adds* the
new increment. The result:

- Frequently-revisited relations stay strong (each visit re-strengthens them).
- Stale relations fade smoothly toward zero without ever being deleted.
- Ranking by `effective_weight` naturally surfaces what matters *now*.

This identical math is used by both the SQLite and MongoDB graph stores, so edge
semantics are backend-independent.

### 3.4 Derived profile / insights

The `InsightEngine` (`engine/insight.py`) rolls the current graph into a
human/LLM-readable `Profile` (`models/profile.py`):

- **`interests`** — top `topic` nodes by cumulative weight.
- **`top_domains`** — top `domain` nodes.
- **`recurring_opinions`** — top `opinion` nodes (with their stored text).
- **`behavior_types`** — archetype mix (`researcher`, `conversationalist`,
  `creator`, `opinionated`, `navigator`) derived from the *decayed* weights of
  the user's outgoing edges, bucketed by relation type and normalized.
- **`decision_patterns`** — heuristics mined from structure, e.g. "researches
  before deciding" (queries that `led_to` pages) and "explores in depth"
  (traces spanning ≥ 3 pages).
- **`summary`** — a one-line natural-language synthesis.

> The topic extractor, behavior classifier, and decision miner are intentionally
> simple, dependency-free heuristics today — each marked `TODO(ml)` with a clean
> seam to drop in a learned model behind the same interface.

---

## 4. How the graph is built

The pipeline for turning a query/behavior into graph + memory runs inside
`Brain.ingest()` (`brain.py`) → `InsightEngine.process_events()` (`insight.py`).
Step by step:

```
1. INGEST          batch of RawEvents arrives (POST /v1/ingest)
2. CAPTURE GATE    _should_capture(): per-category toggle, deny/allow site rules
3. REDACTION       RedactionEngine.apply(): scrub or drop before anything persists
4. PERSIST         EventStore.append(): append-only raw log
5. INSIGHT         process_events(): topic extraction → node/edge upserts (weights)
6. MEMORY          _index_memory(): embed text_for_memory() → VectorStore.add()
7. OUTBOX          enqueue each event for optional (encrypted) cloud sync
```

**Step 5 in detail** — each event type maps to a small set of typed mutations
(all via `observe_edge`, which applies decay+reinforce):

- Any event with a URL upserts a `domain` and `url` node and a
  `domain --contains--> url` edge.
- `visit` → `user --visited--> domain` and `--visited--> url`, then attaches
  topics from `title + content`.
- `dwell` → extra `visited` weight on the url, **log-scaled by dwell time**
  (attention is a stronger signal than a bare visit).
- `click` → a lighter `visited` increment.
- `link` → `url --led_to--> target_url` (the link trail).
- `search` → upsert a `query` node, `user --searched--> query`, attach topics,
  and if a result URL is present, `query --led_to--> url`.
- `llm_chat` → upsert an `llm` node, `user --chatted_with--> llm`, attach topics
  from the message.
- `content_create` → upsert a `document` node, `user --created--> document`.
- `opinion` → upsert an `opinion` node (keyed by md5 of the text),
  `user --holds--> opinion`.

**Topic attachment** (`_attach_topics`) runs `extract_topics()` (a tokenize →
drop stopwords/short tokens → sublinear‑TF top‑N extractor in `engine/topics.py`)
and, for each topic, adds `src --about--> topic` and `user --interested_in-->
topic`. Sessions accumulate `(timestamp, url_id)` pairs that become `Trace`s at
the end of the batch.

**Step 6 in detail** — semantic memory. For each event with non-empty
`text_for_memory()`, the brain embeds the text and stores
`(id, embedding, text, metadata)` in the `VectorStore`. Metadata keeps `type`,
`url`, `title`, `domain`, `timestamp` so recall results are self-describing. The
default `HashingEmbeddingProvider` is a deterministic feature-hashing
bag-of-words model (zero deps, zero network); `sentence_transformers` and
`openai` providers are drop-in via config.

```
            ┌──────────────┐   topics/nodes/edges   ┌──────────────┐
 RawEvent ─▶│ InsightEngine │ ─────────────────────▶ │  GraphStore   │
            └──────┬────────┘                        └──────────────┘
                   │ text_for_memory()
                   ▼
            ┌──────────────┐   embedding vector     ┌──────────────┐
            │  Embeddings   │ ─────────────────────▶ │  VectorStore  │
            └──────────────┘                         └──────────────┘
```

---

## 5. Recall & ask: RAG over graph + vector

The two read paths combine the **two indexes** — semantic memory (vectors) and
the knowledge graph (structure) — so retrieval is grounded both by meaning *and*
by your modeled interests.

**`search_memory(query, k)`** — pure semantic recall: embed the query, cosine
top-k against the `VectorStore`, return `(id, score, text, metadata)`.

**`recall(query, k)`** — semantic recall **fused with graph context**:

```python
async def recall(self, query, k=5):
    memories = await self.search_memory(query, k)        # vector search
    related_topics = []
    for topic in extract_topics(query, max_n=5):          # graph entry points
        node = await self.graph.find_node(NodeType.TOPIC, topic)   # O(1) by (type,key)
        if not node: continue
        neighbors = await self.graph.neighbors(node.id, limit=5)   # ranked by decayed weight
        related_topics.append({...})
    return {"query": query, "memories": memories, "graph_context": related_topics}
```

So the query's topics are looked up as graph entry points, and each topic's
strongest (most recently reinforced) neighbors are returned alongside the vector
hits.

**`ask(question, k)`** — RAG: it calls `recall()` + `get_profile()`, assembles a
context block (top memories + related interests + profile summary), and produces
an answer. In `brain-core` the synthesis is **templated by default** (zero
network, marked `TODO(ml)`); the Web API layers **OpenAI synthesis** on top when
`OPENAI_API_KEY` is set — `synthesized_by` flips from `"template"` to `"openai"`
and `answer` is replaced. Either way the structured `sources` and `graph_context`
are returned for transparency.

```
question
   │
   ├─▶ extract topics ─▶ graph.find_node ─▶ neighbors (decayed-weight ranked) ─┐
   │                                                                            ├─▶ context
   └─▶ embed ─▶ vector top-k (cosine) ─────────────────────────────────────────┘
                                                                                 │
                                          profile summary ──────────────────────┤
                                                                                 ▼
                              template answer  (or OpenAI synthesis in the BFF)
```

---

## 6. Fast traversal & scalability

### Indexing strategy

The default relational schema (`storage/db.py`) is indexed exactly for the hot
paths:

| Table | Index | Used by |
| --- | --- | --- |
| `nodes` | **unique `(type, key)`** | `upsert_node` / `find_node` — O(1) dedup + topic entry points for recall |
| `edges` | index on `src`; **unique `(src, dst, relation)`** | `observe_edge` upsert and `neighbors()` traversal |
| `events` | index on `timestamp` | `recent` / `since` / retention pruning |
| `traces` | index on `session_id` | session reconstruction |
| `outbox` | index on `status` | sync worker draining pending rows |

The MongoDB graph store mirrors these exactly: `graph_nodes` unique on
`(type, key)`, `graph_edges` unique on `(src, dst, relation)` + index on `src`,
`traces` indexed on `session_id`, `events` indexed on `timestamp`.

**Traversal** is "fetch outgoing edges from `src` (indexed), join target nodes,
compute `effective_weight`, sort descending, take `limit`." Because ranking uses
the **decayed** weight, the most relevant *current* neighbors come first — this
is the relevance signal the profile, `recall`, and the dashboard all rely on.

### Swappable storage tiers

Everything is chosen in one place — `factory.py` — from `Settings.storage`:

| Tier | Default (local) | Bundled opt-in | Documented/roadmap |
| --- | --- | --- | --- |
| **Event store** | `sqlite` | `mongodb` | `postgres` (drop-in via DSN — `SqlEventStore` is dialect-agnostic) |
| **Graph store** | `sqlite` | `mongodb` | `postgres` (same async SQLAlchemy core), `neo4j` / `kuzu` (`TODO(scale)`) |
| **Vector store** | `numpy` (in-process, exact cosine) | `chroma`, `mongodb` | `qdrant`, `pgvector` (`TODO(scale)`) |
| **Embeddings** | `hashing` | `sentence_transformers`, `openai` | — |

Config knobs: `storage.event_backend`, `storage.graph_backend`,
`storage.vector_backend`, plus `postgres_dsn`, `chroma_path`, `qdrant_url`,
`neo4j_uri`, `mongo_uri`, `mongo_db`. Backends can be **mixed** (e.g. Mongo graph
+ numpy vectors). Adding a backend = implement the ABC + add a branch in the
factory; nothing else in the codebase changes.

### How to scale each tier

- **Events**: SQLite → Postgres (set `postgres_dsn`) or MongoDB (`event_backend:
  mongodb`). Range scans use the `timestamp` index; retention pruning is a single
  delete by cutoff.
- **Graph**: SQLite → Postgres for bigger relational graphs, or Mongo for
  horizontal scaling. For native multi-hop traversal at very large scale, drop in
  a Neo4j/Kùzu adapter behind `GraphStore` (the embedded relational traversal is
  fine into the low millions of edges).
- **Vectors**: numpy (exact brute-force, perfect for local) → Chroma locally, or
  Qdrant/pgvector for ANN at scale. On **MongoDB Atlas**, swap the brute-force
  `query()` for a `$vectorSearch` aggregation backed by an Atlas Vector Search
  index over the `embedding` field (`"numDimensions": dim`,
  `"similarity": "cosine"`); the drop-in snippet is in the docstring of
  `storage/mongo/vector_store.py`. The brute-force path stays correct for
  self-hosted Mongo without that feature.

### Decayed-weight ranking for relevance

Because edges store raw weight + `last_seen` and decay on read, **relevance is
recomputed continuously** without a batch job: `neighbors()`, `top_nodes()`, and
`dump_graph()` rank by current effective weight. This is the unifying mechanism
behind recall ordering, profile interests, behavior archetypes, and the size of
nodes in the 3D dashboard graph.

---

## 7. Auth & data flow

### Local-first storage

By default everything lives on your machine: the Core Brain writes SQLite +
numpy vectors under `./.brain`; the Web API writes users/keys/usage to
`./.brain/web/web.db`. Nothing leaves the device unless you opt into cloud sync.

### Outbox → cloud sync (optional, encrypted)

Each accepted event is also enqueued in a durable **outbox** (`OutboxStore`).
A `SyncWorker` (`sync/worker.py`) drains it on an interval:

- In `mode: local` (default) the client is a `NoopCloudClient` — rows are logged
  and dropped; nothing leaves the machine.
- In `mode: cloud_sync` with `cloud.endpoint` set, an `HttpCloudClient` POSTs
  batches to `<endpoint>/v1/sync`. Each payload is **encrypted at rest with
  Fernet** (`sync/crypto.py`) using `cloud.encryption_key` (or an ephemeral key
  generated under `data_dir` and printed once). Rows are only marked sent on
  success, so failures retry and nothing is lost.

```
ingest ─▶ OutboxStore.enqueue ─▶ [interval] SyncWorker.drain_once
                                      │ encrypt (Fernet) if cloud_sync
                                      ▼
                                HttpCloudClient ─▶ POST <endpoint>/v1/sync
                                      │ on success
                                      ▼
                                mark_sent (else retry next tick)
```

The receiving cloud service (auth, storage, online search) is intentionally out
of scope (`TODO(cloud)`).

### Authentication (Google OAuth is the primary mechanism)

The Web API/BFF (`packages/web/api`) owns all authentication; the Core Brain
trusts its localhost caller. There are three identities in play:

1. **Dashboard user (browser).** `GET /auth/google/login` → Google consent →
   `GET /auth/google/callback` verifies the token, upserts the user
   (`google_sub`, email, name, picture), and sets a **signed session cookie**.
   The React frontend (`:4000`) then calls `/api/*` with that cookie.

2. **MCP server & browser extension (programmatic clients).** The documented
   primary path is **Google OAuth bearer tokens**: a client signs in with Google
   and sends `Authorization: Bearer <Google OAuth token>` on each request; the
   Web API verifies the token against Google and resolves the owning user before
   proxying to the brain.
   - The browser extension already performs Google sign-in via
     `chrome.identity.launchWebAuthFlow` (implicit flow, no client secret),
     obtaining a Google access token (`background/auth.ts`).
   - The MCP server signs in once (a one-time **`login`** step) and reuses the
     resulting token — no long-lived API keys to mint or paste.

3. **Legacy API keys (`X-API-Key`).** The repo still contains the API-key path:
   keys are minted in the dashboard, stored only as a SHA-256 hash + short
   prefix, and verified by `require_auth` / `require_api_key`. This path may
   still exist for backward compatibility, but **OAuth bearer is the documented,
   forward-looking mechanism** for both the extension and MCP.

The shared guard `require_auth` accepts a session cookie *or* a programmatic
credential and resolves a user for every `/api/*` data endpoint; `require_user`
is session-only (used for key management); CORS allows the `:4000` origin
(credentialed) and `chrome-extension://*`, permitting `Authorization` and
`X-API-Key` headers.

```
 Browser (4000) ──cookie──────────────┐
 Extension      ──Bearer <google tok>─┤
 MCP server     ──Bearer <google tok>─┼─▶ Web API (5050)  ── verify identity ──▶ proxy ─▶ Core Brain (8077)
 (legacy)       ──X-API-Key──────────┘     require_auth                          /v1/*
```

See [DEPLOYMENT.md](./DEPLOYMENT.md) for the exact Google Cloud Console setup and
[VALIDATION_AND_SKILLS.md](./VALIDATION_AND_SKILLS.md) for OAuth security checks.

---

## 8. Privacy & redaction

Redaction is the **privacy gate every event passes through before it is stored
or embedded**, and it happens in two places (defense in depth):

- **Client-side**, in the browser extension's background worker
  (`common/redaction.ts`) — credit cards (Luhn-validated), SSNs, OpenAI/
  Anthropic/Stripe/AWS/GitHub/Google keys, JWTs, bearer tokens, isitme keys, and
  any `key=value` whose key looks sensitive. The background worker is the single
  chokepoint: content scripts only emit candidates.
- **Server-side**, in `RedactionEngine` (`redaction/engine.py`) — built-in
  detectors for `passwords`, `banking`, `health`, `secrets`, and `pii`, plus
  user-supplied `custom_patterns`. It also enforces site rules:
  - `deny_sites` → event dropped entirely (never stored);
  - `content_blocklist_sites` → content/title scrubbed, metadata kept;
  - `allow_sites` → if non-empty, only those domains are captured.

The capture gate (`Brain._should_capture`) and per-category toggles run *before*
redaction, so disabled categories and denied sites never even reach the scrubber.
Detectors are conservative by design — over-redaction beats leaking.

---

## 9. Cross-references

- Core Brain internals & backends → [`packages/brain-core/README.md`](./packages/brain-core/README.md)
- Web product (run all three services) → [`packages/web/README.md`](./packages/web/README.md)
- Web API auth contract & endpoints → [`packages/web/api/README.md`](./packages/web/api/README.md)
- MCP tools & connectors → [`packages/brain-mcp/README.md`](./packages/brain-mcp/README.md)
- Extension capture & privacy → [`packages/browser-extension/README.md`](./packages/browser-extension/README.md)
- Operator guide → [DEPLOYMENT.md](./DEPLOYMENT.md)
- Validation & skills → [VALIDATION_AND_SKILLS.md](./VALIDATION_AND_SKILLS.md)
- Example config → [`config.example.yaml`](./config.example.yaml)
