"""FastAPI app factory + routes for the Core Brain.

Endpoints (all JSON):

    POST /v1/ingest         batch of raw events  -> ingest summary
    POST /v1/log            single event         -> ingest summary
    POST /v1/recall         {query,k}            -> memories + graph context
    POST /v1/search_memory  {query,k}            -> semantic hits
    GET  /v1/profile                              -> derived Profile
    GET  /v1/graph                                -> read-only nodes + edges export
    POST /v1/ask            {question,k}         -> RAG answer + sources
    GET  /v1/stats                                -> store counters
    GET  /healthz                                 -> liveness
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from pydantic import BaseModel, Field

from brain_core.brain import Brain
from brain_core.config import Settings, load_settings
from brain_core.models.events import EventBatch, RawEvent
from brain_core.models.profile import Profile
from brain_core.sync.worker import build_worker

logger = logging.getLogger("brain.api")


class QueryRequest(BaseModel):
    query: str
    k: int = Field(default=5, ge=1, le=50)


class AskRequest(BaseModel):
    question: str
    k: int = Field(default=6, ge=1, le=50)


def get_brain(request: Request) -> Brain:
    return request.app.state.brain


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        brain = Brain(settings)
        await brain.startup()
        app.state.brain = brain
        worker = build_worker(settings)
        await worker._outbox.init()
        worker_task = asyncio.create_task(worker.run())
        logger.info("Core Brain ready (mode=%s).", settings.mode)
        try:
            yield
        finally:
            worker.stop()
            worker_task.cancel()
            await brain.shutdown()

    app = FastAPI(
        title="isitme — Core Brain",
        version="0.1.0",
        description="Local-first personal cognition layer.",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/v1/stats")
    async def stats(brain: Brain = Depends(get_brain)) -> dict:
        return await brain.stats()

    @app.post("/v1/ingest")
    async def ingest(batch: EventBatch, brain: Brain = Depends(get_brain)) -> dict:
        return await brain.ingest(batch)

    @app.post("/v1/log")
    async def log_one(event: RawEvent, brain: Brain = Depends(get_brain)) -> dict:
        return await brain.ingest(EventBatch(client="api", events=[event]))

    @app.post("/v1/recall")
    async def recall(req: QueryRequest, brain: Brain = Depends(get_brain)) -> dict:
        return await brain.recall(req.query, req.k)

    @app.post("/v1/search_memory")
    async def search_memory(req: QueryRequest, brain: Brain = Depends(get_brain)) -> dict:
        return {"results": await brain.search_memory(req.query, req.k)}

    @app.get("/v1/profile")
    async def profile(brain: Brain = Depends(get_brain)) -> Profile:
        return await brain.get_profile()

    @app.get("/v1/graph")
    async def graph(
        node_limit: int = 1500,
        edge_limit: int = 4000,
        brain: Brain = Depends(get_brain),
    ) -> dict:
        """Read-only export of the knowledge graph (nodes + decayed edges)."""
        nodes, edges = await brain.graph.dump_graph(node_limit, edge_limit)
        return {
            "nodes": [n.model_dump(mode="json") for n in nodes],
            "edges": [e.model_dump(mode="json") for e in edges],
        }

    @app.post("/v1/ask")
    async def ask(req: AskRequest, brain: Brain = Depends(get_brain)) -> dict:
        return await brain.ask(req.question, req.k)

    return app
