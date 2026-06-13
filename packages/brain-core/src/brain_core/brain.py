"""The Brain — orchestrates storage, redaction, insight, and query.

This is the heart of the Core service and the only stateful component. It wires
the pluggable backends together and exposes the high-level operations the API
and MCP server call: ``ingest``, ``recall``, ``search_memory``, ``get_profile``,
and ``ask``.
"""

from __future__ import annotations

from datetime import timedelta
from fnmatch import fnmatch
from typing import Any

from brain_core import factory
from brain_core.config import Settings
from brain_core.engine.decay import utcnow
from brain_core.engine.insight import InsightEngine
from brain_core.engine.topics import extract_topics
from brain_core.models.events import EventBatch, RawEvent
from brain_core.models.graph import NodeType, RelationType
from brain_core.models.profile import Profile
from brain_core.redaction.engine import RedactionEngine


class Brain:
    def __init__(self, settings: Settings):
        self._settings = settings
        self.events = factory.build_event_store(settings)
        self.graph = factory.build_graph_store(settings)
        self.vectors = factory.build_vector_store(settings)
        self.outbox = factory.build_outbox(settings)
        self.embeddings = factory.build_embeddings(settings)
        self.redactor = RedactionEngine(settings.redaction)
        self.insight = InsightEngine(self.graph, settings.graph)

    async def startup(self) -> None:
        await self.events.init()
        await self.graph.init()
        await self.vectors.init(self.embeddings.dim)
        await self.outbox.init()

    async def shutdown(self) -> None:
        await self.events.close()
        await self.graph.close()
        await self.vectors.close()
        await self.outbox.close()

    # --- capture gating -----------------------------------------------------
    def _should_capture(self, event: RawEvent) -> bool:
        cap = self._settings.capture
        if not cap.categories.get(event.type.value, True):
            return False
        domain = event.domain
        if domain:
            if any(fnmatch(domain, p) for p in cap.deny_sites):
                return False
            if cap.allow_sites and not any(fnmatch(domain, p) for p in cap.allow_sites):
                return False
        return True

    # --- ingestion ----------------------------------------------------------
    async def ingest(self, batch: EventBatch) -> dict[str, Any]:
        accepted: list[RawEvent] = []
        dropped = 0
        redactions = 0
        for event in batch.events:
            if not self._should_capture(event):
                dropped += 1
                continue
            result = self.redactor.apply(event)
            if result.dropped or result.event is None:
                dropped += 1
                continue
            redactions += result.redaction_count
            accepted.append(result.event)

        if not accepted:
            return {"accepted": 0, "dropped": dropped, "redactions": redactions}

        await self.events.append(accepted)
        stats = await self.insight.process_events(accepted)
        await self._index_memory(accepted)
        for event in accepted:
            await self.outbox.enqueue("event", event.model_dump(mode="json"))

        return {
            "accepted": len(accepted),
            "dropped": dropped,
            "redactions": redactions,
            "by_type": stats,
        }

    async def _index_memory(self, events: list[RawEvent]) -> None:
        ids, texts, metas = [], [], []
        for event in events:
            text = event.text_for_memory()
            if not text:
                continue
            ids.append(event.id)
            texts.append(text)
            metas.append(
                {
                    "type": event.type.value,
                    "url": event.url,
                    "title": event.title,
                    "domain": event.domain,
                    "timestamp": event.timestamp.isoformat(),
                }
            )
        if not ids:
            return
        embeddings = await self.embeddings.embed(texts)
        await self.vectors.add(ids, embeddings, texts, metas)

    # --- queries ------------------------------------------------------------
    async def search_memory(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        embedding = await self.embeddings.embed_one(query)
        hits = await self.vectors.query(embedding, k)
        return [
            {"id": _id, "score": round(score, 4), "text": text, "metadata": meta}
            for _id, score, text, meta in hits
        ]

    async def recall(self, query: str, k: int = 5) -> dict[str, Any]:
        """Pull together semantic memories + related graph context for a query."""
        memories = await self.search_memory(query, k)
        related_topics: list[dict[str, Any]] = []
        for topic in extract_topics(query, max_n=5):
            node = await self.graph.find_node(NodeType.TOPIC, topic)
            if not node:
                continue
            neighbors = await self.graph.neighbors(node.id, limit=5)
            related_topics.append(
                {
                    "topic": node.label,
                    "weight": round(node.weight, 3),
                    "related": [
                        {
                            "label": n.label,
                            "type": n.type.value,
                            "weight": round(e.effective_weight or 0.0, 3),
                        }
                        for e, n in neighbors
                    ],
                }
            )
        return {"query": query, "memories": memories, "graph_context": related_topics}

    async def get_profile(self) -> Profile:
        count = await self.events.count()
        return await self.insight.build_profile(count)

    async def ask(self, question: str, k: int = 6) -> dict[str, Any]:
        """RAG over graph + vector memory.

        Retrieval is fully implemented; final natural-language *synthesis* is
        templated by default (zero-network). Configure an LLM to generate prose.
        TODO(ml): plug an LLM here to synthesize over `context`.
        """
        recall = await self.recall(question, k)
        profile = await self.get_profile()
        context_lines = [f"- {m['text'][:200]}" for m in recall["memories"]]
        topic_line = ", ".join(t["topic"] for t in recall["graph_context"]) or "n/a"
        answer = (
            f"Based on your captured memory, here is what's relevant to "
            f'"{question}":\n'
            f"Related interests: {topic_line}.\n"
            f"Top matching memories:\n" + ("\n".join(context_lines) or "  (no memories yet)")
        )
        return {
            "question": question,
            "answer": answer,
            "synthesized_by": "template",  # swap to LLM via config
            "sources": recall["memories"],
            "graph_context": recall["graph_context"],
            "profile_summary": profile.summary,
        }

    # --- maintenance --------------------------------------------------------
    async def apply_retention(self) -> int:
        days = self._settings.capture.retention_days
        if days <= 0:
            return 0
        cutoff = utcnow() - timedelta(days=days)
        return await self.events.prune_before(cutoff)

    async def stats(self) -> dict[str, Any]:
        return {
            "events": await self.events.count(),
            "nodes": await self.graph.node_count(),
            "edges": await self.graph.edge_count(),
            "memories": await self.vectors.count(),
            "outbox_pending": await self.outbox.pending_count(),
            "mode": self._settings.mode,
            "embedding_provider": self._settings.embedding.provider,
        }
