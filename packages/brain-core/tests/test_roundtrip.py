"""End-to-end core tests: ingest -> graph update -> recall round-trip.

Covers the contract the whole product rests on: events become graph structure
and semantic memory, redaction happens before storage, capture filters drop
unwanted events, and edge weights decay over time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from brain_core.engine.decay import effective_weight, reinforce
from brain_core.models.events import EventBatch, EventType, RawEvent
from brain_core.models.graph import NodeType, RelationType


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sample_batch() -> EventBatch:
    base = _now()
    return EventBatch(
        client="test",
        events=[
            RawEvent(
                type=EventType.SEARCH,
                timestamp=base,
                source="browser",
                session_id="s1",
                data={"query": "rust async runtime tokio"},
            ),
            RawEvent(
                type=EventType.VISIT,
                timestamp=base + timedelta(seconds=5),
                source="browser",
                session_id="s1",
                url="https://docs.rs/tokio/latest/tokio/",
                title="Tokio async runtime documentation",
                content="Tokio is an asynchronous runtime for the Rust programming language.",
            ),
            RawEvent(
                type=EventType.DWELL,
                timestamp=base + timedelta(seconds=40),
                source="browser",
                session_id="s1",
                url="https://docs.rs/tokio/latest/tokio/",
                title="Tokio async runtime documentation",
                data={"dwell_ms": 35000},
            ),
            RawEvent(
                type=EventType.OPINION,
                timestamp=base + timedelta(seconds=60),
                source="cursor",
                content="I think async Rust is powerful but has a steep learning curve.",
            ),
        ],
    )


async def test_ingest_builds_graph_and_memory(brain):
    result = await brain.ingest(sample_batch())
    assert result["accepted"] == 4
    assert result["dropped"] == 0

    stats = await brain.stats()
    assert stats["events"] == 4
    assert stats["nodes"] > 0
    assert stats["edges"] > 0
    assert stats["memories"] >= 2  # search + visit produced memory text
    assert stats["outbox_pending"] == 4  # outbox enqueued each event

    # A topic node for "tokio" / "rust" should exist and connect to the user.
    user = await brain.graph.find_node(NodeType.USER, "me")
    assert user is not None
    interests = await brain.graph.neighbors(user.id, RelationType.INTERESTED_IN, limit=20)
    topics = {node.label for _, node in interests}
    assert any(t in topics for t in ("tokio", "rust", "async", "runtime"))


async def test_recall_round_trip(brain):
    await brain.ingest(sample_batch())
    recall = await brain.recall("asynchronous rust programming", k=5)
    assert recall["memories"], "expected at least one semantic memory hit"
    texts = " ".join(m["text"].lower() for m in recall["memories"])
    assert "tokio" in texts or "rust" in texts


async def test_profile_derivation(brain):
    await brain.ingest(sample_batch())
    profile = await brain.get_profile()
    assert profile.event_count == 4
    assert profile.interests, "profile should surface interests"
    assert profile.behavior_types, "profile should classify behavior"
    assert profile.recurring_opinions, "opinion event should appear in profile"
    assert "async" in profile.summary.lower() or profile.summary


async def test_ask_returns_answer_and_sources(brain):
    await brain.ingest(sample_batch())
    answer = await brain.ask("what do I know about tokio?")
    assert answer["answer"]
    assert answer["synthesized_by"] == "template"
    assert isinstance(answer["sources"], list)


async def test_redaction_before_storage(brain):
    batch = EventBatch(
        client="test",
        events=[
            RawEvent(
                type=EventType.CONTENT_CREATE,
                title="notes",
                content="my password: hunter2 and email me@example.com",
            )
        ],
    )
    await brain.ingest(batch)
    recent = await brain.events.recent(10)
    assert recent, "event should be stored"
    stored = recent[0].content
    assert "hunter2" not in stored
    assert "me@example.com" not in stored
    assert "[REDACTED]" in stored


async def test_capture_deny_site_filter(tmp_path):
    from brain_core.brain import Brain
    from brain_core.config import Settings

    settings = Settings(data_dir=str(tmp_path / "b"), mode="local")
    settings.capture.deny_sites = ["secret.example.com"]
    b = Brain(settings)
    await b.startup()
    try:
        batch = EventBatch(
            client="test",
            events=[
                RawEvent(type=EventType.VISIT, url="https://secret.example.com/x", title="x"),
                RawEvent(type=EventType.VISIT, url="https://ok.example.com/y", title="y"),
            ],
        )
        result = await b.ingest(batch)
        assert result["accepted"] == 1
        assert result["dropped"] == 1
    finally:
        await b.shutdown()


def test_edge_decay_math():
    now = _now()
    # An edge observed 30 days ago with half-life 30d should decay to ~half.
    old = now - timedelta(days=30)
    decayed = effective_weight(1.0, old, now, half_life_days=30.0)
    assert 0.49 < decayed < 0.51

    # Reinforcing decays the prior then adds the increment.
    new_weight = reinforce(1.0, old, 1.0, now, half_life_days=30.0)
    assert 1.49 < new_weight < 1.51


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.github.com/a/b", "github.com"),
        ("https://docs.rs/tokio", "docs.rs"),
        (None, None),
    ],
)
def test_domain_extraction(url, expected):
    assert RawEvent(type=EventType.VISIT, url=url).domain == expected
