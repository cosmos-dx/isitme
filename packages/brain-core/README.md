# brain-core

The **Core Brain** of `isitme` — the only stateful service. It ingests
behavioral events, models them as a weighted, time-decaying knowledge graph,
stores semantic memory, derives a profile, and serves recall/RAG queries.

Local-first: the default backends (SQLite + in-process numpy vectors + hashing
embeddings) run with **zero network and zero API keys**.

## Install & run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e "packages/brain-core[dev]"

brain serve            # start the HTTP API (default 127.0.0.1:8077)
brain stats            # print store counters
brain sync             # run the standalone outbox sync worker
pytest packages/brain-core      # run the test suite
```

## Layout

```
src/brain_core/
  config.py        # pydantic-settings + YAML loader (shared with brain-mcp)
  models/          # RawEvent / Node / Edge / Trace / Profile
  storage/         # ABCs + SQLite event/graph/outbox + numpy/chroma vectors
  embeddings/      # EmbeddingProvider ABC + hashing/ST/OpenAI impls
  redaction/       # privacy gate (runs before storage)
  engine/          # decay math, topic extraction, InsightEngine, profile
  sync/            # CloudClient interface + encryption + SyncWorker
  api/             # FastAPI app + routes
  brain.py         # orchestrator
  factory.py       # config -> concrete backends
```

## Storage backends

Everything is pluggable behind the ABCs in `storage/base.py`. The default is
local-first (SQLite + numpy vectors). MongoDB is a bundled opt-in backend.

### MongoDB (opt-in)

```bash
docker compose up -d mongodb          # from the repo root
```

Then in `config.yaml`:

```yaml
storage:
  event_backend: "mongodb"
  graph_backend: "mongodb"
  vector_backend: "mongodb"
  mongo_uri: "mongodb://localhost:27017"
  mongo_db: "isitme"
```

…or via env vars (no file needed):

```bash
BRAIN_STORAGE__EVENT_BACKEND=mongodb \
BRAIN_STORAGE__GRAPH_BACKEND=mongodb \
BRAIN_STORAGE__VECTOR_BACKEND=mongodb \
BRAIN_STORAGE__MONGO_URI=mongodb://localhost:27017 \
brain serve
```

Backends can be mixed (e.g. Mongo graph + numpy vectors). Collections created:
`events`, `graph_nodes` (unique `(type,key)`), `graph_edges`
(unique `(src,dst,relation)`, indexed on `src`), `traces` (indexed on
`session_id`), and `vectors` (embeddings stored as float arrays). The Mongo
graph store reuses the exact time-decay math in `engine/decay.py`, so edge
semantics are identical to SQLite.

**Vector search:** the bundled `MongoVectorStore` does exact brute-force cosine
in-process with numpy. On MongoDB Atlas, swap `query()` to a `$vectorSearch`
aggregation backed by an Atlas Vector Search index — the docstring in
`storage/mongo/vector_store.py` has the drop-in snippet.

`motor` is a dependency, but no Mongo server is needed for the default
SQLite/numpy path.

See the repo root `README.md` and `ARCHITECTURE.md` for the full model.
