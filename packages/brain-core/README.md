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

See the repo root `README.md` and `ARCHITECTURE.md` for the full model.
