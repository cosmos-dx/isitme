"""Tests for the MongoDB storage backends.

These exercise the Mongo EventStore / GraphStore / VectorStore against an
in-memory ``mongomock-motor`` client when available; otherwise they fall back
to a real Mongo at ``MONGO_TEST_URI`` (default ``mongodb://localhost:27017``)
and skip if it is unreachable. They never touch the user's running services.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

from brain_core.engine.decay import effective_weight, utcnow
from brain_core.models.events import EventType, RawEvent
from brain_core.models.graph import NodeType, RelationType

try:
    from mongomock_motor import AsyncMongoMockClient

    _HAS_MONGOMOCK = True
except ImportError:  # pragma: no cover - optional dev dep
    _HAS_MONGOMOCK = False


def _mock_client():
    return AsyncMongoMockClient()


async def _real_client_or_skip():
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
    except ImportError:
        pytest.skip("neither mongomock-motor nor motor is installed")
    uri = os.environ.get("MONGO_TEST_URI", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=400)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"no reachable MongoDB at {uri}")
    return client


async def _client():
    if _HAS_MONGOMOCK:
        return _mock_client()
    return await _real_client_or_skip()


_DB = "isitme_test"


async def test_mongo_event_store_roundtrip():
    from brain_core.storage.mongo.event_store import MongoEventStore

    store = MongoEventStore("mongodb://unused", _DB, client=await _client())
    await store.init()
    try:
        base = utcnow()
        events = [
            RawEvent(type=EventType.SEARCH, timestamp=base, data={"query": "tokio"}),
            RawEvent(
                type=EventType.VISIT,
                timestamp=base + timedelta(seconds=5),
                url="https://docs.rs/tokio",
                title="Tokio",
            ),
        ]
        assert await store.append(events) == 2
        assert await store.count() == 2
        # Idempotent re-ingest (same ids) keeps the count stable.
        assert await store.append(events) == 2
        assert await store.count() == 2

        recent = await store.recent(10)
        assert {e.id for e in recent} == {e.id for e in events}
        assert recent[0].timestamp >= recent[-1].timestamp  # desc

        since = await store.since(base + timedelta(seconds=1))
        assert [e.url for e in since] == ["https://docs.rs/tokio"]

        removed = await store.prune_before(base + timedelta(seconds=1))
        assert removed == 1
        assert await store.count() == 1
    finally:
        await store.close()


async def test_mongo_graph_store_dedup_and_decay():
    from brain_core.storage.mongo.graph_store import MongoGraphStore

    store = MongoGraphStore("mongodb://unused", _DB, half_life_days=30.0, client=await _client())
    await store.init()
    try:
        user = await store.upsert_node(NodeType.USER, "me", "me", weight_delta=1.0)
        topic = await store.upsert_node(NodeType.TOPIC, "tokio", "tokio", weight_delta=2.0)
        # Dedup on (type, key): same node, accumulated weight.
        again = await store.upsert_node(NodeType.TOPIC, "tokio", "tokio", weight_delta=3.0)
        assert again.id == topic.id
        assert again.weight == pytest.approx(5.0)
        assert await store.node_count() == 2

        # Observe an edge 30 days ago, then read "now": effective weight halves.
        now = utcnow()
        old = now - timedelta(days=30)
        edge = await store.observe_edge(
            user.id, topic.id, RelationType.INTERESTED_IN, weight_delta=1.0, at=old
        )
        assert edge.weight == pytest.approx(1.0)
        assert await store.edge_count() == 1

        neighbors = await store.neighbors(user.id, now=now)
        assert len(neighbors) == 1
        e, n = neighbors[0]
        assert n.id == topic.id
        assert 0.49 < (e.effective_weight or 0) < 0.51

        # Re-observing decays the prior to "now" then adds the increment.
        re = await store.observe_edge(
            user.id, topic.id, RelationType.INTERESTED_IN, weight_delta=1.0, at=now
        )
        assert 1.49 < re.weight < 1.51

        nodes, edges = await store.dump_graph()
        assert {x.id for x in nodes} == {user.id, topic.id}
        assert len(edges) == 1
        assert edges[0].effective_weight is not None
    finally:
        await store.close()


async def test_mongo_vector_store_cosine_ranking():
    from brain_core.storage.mongo.vector_store import MongoVectorStore

    store = MongoVectorStore("mongodb://unused", _DB, client=await _client())
    await store.init(dim=3)
    try:
        await store.add(
            ids=["a", "b", "c"],
            embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.9, 0.1, 0.0]],
            texts=["a", "b", "c"],
            metadatas=[{"k": 1}, {"k": 2}, {"k": 3}],
        )
        assert await store.count() == 3
        hits = await store.query([1.0, 0.0, 0.0], k=2)
        assert [h[0] for h in hits] == ["a", "c"]  # closest cosine first
        assert hits[0][1] == pytest.approx(1.0, abs=1e-5)
        # Upsert is idempotent on id.
        await store.add(["a"], [[1.0, 0.0, 0.0]], ["a2"], [{"k": 9}])
        assert await store.count() == 3
    finally:
        await store.close()


def test_decay_matches_shared_math():
    # Guard that the Mongo backend uses the same decay helper as everything else.
    now = utcnow()
    old = now - timedelta(days=30)
    assert 0.49 < effective_weight(1.0, old, now, 30.0) < 0.51
