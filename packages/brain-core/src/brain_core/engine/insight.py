"""Insight engine — rolls events into graph updates and a derived profile.

Pipeline (intentionally simple but real, and fully documented):

    events ──▶ graph updates (typed nodes + strengthen/decay edges + traces)
           ──▶ profile rollup (interests, behavior types, decision patterns,
                                recurring opinions)

Each event type maps to a small set of node/edge mutations (see ``process_events``).
Edges are *observed* (strengthened with decay) rather than overwritten, so the
graph naturally reflects recency-weighted importance. Profile derivation reads
the top decayed nodes/edges back out.

TODO(ml): the topic model, behavior-type classifier, and decision-pattern miner
are heuristic. Each has a clean seam to drop in a learned model later.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import datetime

from brain_core.config import GraphSettings
from brain_core.engine.topics import extract_topics
from brain_core.models.events import EventType, RawEvent
from brain_core.models.graph import NodeType, RelationType, Trace
from brain_core.models.profile import Interest, Opinion, Profile
from brain_core.storage.base import GraphStore

USER_KEY = "me"

# Maps the domains/event-mix into coarse behavior archetypes.
_BEHAVIOR_SIGNALS: dict[str, set[EventType]] = {
    "researcher": {EventType.SEARCH, EventType.VISIT, EventType.DWELL},
    "conversationalist": {EventType.LLM_CHAT},
    "creator": {EventType.CONTENT_CREATE},
    "opinionated": {EventType.OPINION},
    "navigator": {EventType.LINK, EventType.CLICK},
}


class InsightEngine:
    def __init__(self, graph: GraphStore, settings: GraphSettings):
        self._graph = graph
        self._settings = settings
        self._user_id: str | None = None

    async def _user(self) -> str:
        if self._user_id is None:
            node = await self._graph.upsert_node(NodeType.USER, USER_KEY, "You")
            self._user_id = node.id
        return self._user_id

    async def _topic_node(self, topic: str) -> str:
        node = await self._graph.upsert_node(
            NodeType.TOPIC, topic, topic, weight_delta=0.5
        )
        return node.id

    async def _attach_topics(self, src_id: str, text: str | None, at: datetime) -> None:
        user_id = await self._user()
        for topic in extract_topics(text, self._settings.max_topics_per_event):
            topic_id = await self._topic_node(topic)
            await self._graph.observe_edge(src_id, topic_id, RelationType.ABOUT, 1.0, at)
            await self._graph.observe_edge(
                user_id, topic_id, RelationType.INTERESTED_IN, 0.5, at
            )

    async def process_events(self, events: list[RawEvent]) -> dict[str, int]:
        """Apply all graph mutations for a batch. Returns simple counters."""
        w = self._settings.default_edge_weight
        user_id = await self._user()
        sessions: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        stats = Counter()

        for event in events:
            at = event.timestamp
            url_id: str | None = None
            domain_id: str | None = None

            if event.url and event.domain:
                domain_id = (
                    await self._graph.upsert_node(
                        NodeType.DOMAIN, event.domain, event.domain, weight_delta=w
                    )
                ).id
                url_id = (
                    await self._graph.upsert_node(
                        NodeType.URL, event.url, event.title or event.url, weight_delta=w
                    )
                ).id
                await self._graph.observe_edge(
                    domain_id, url_id, RelationType.CONTAINS, w, at
                )

            if event.type == EventType.VISIT and domain_id and url_id:
                await self._graph.observe_edge(user_id, domain_id, RelationType.VISITED, w, at)
                await self._graph.observe_edge(user_id, url_id, RelationType.VISITED, w, at)
                await self._attach_topics(url_id, f"{event.title}\n{event.content}", at)

            elif event.type == EventType.DWELL and url_id:
                dwell_ms = float(event.data.get("dwell_ms", 0) or 0)
                # Dwell time is an attention signal -> extra weight (log-scaled seconds).
                bonus = w * (1.0 + min(3.0, (dwell_ms / 1000.0) ** 0.5 / 3.0))
                await self._graph.observe_edge(user_id, url_id, RelationType.VISITED, bonus, at)

            elif event.type == EventType.CLICK and url_id:
                await self._graph.observe_edge(user_id, url_id, RelationType.VISITED, w * 0.5, at)

            elif event.type == EventType.LINK and url_id:
                target = event.data.get("target_url")
                if target:
                    target_id = (
                        await self._graph.upsert_node(NodeType.URL, target, target, weight_delta=w)
                    ).id
                    await self._graph.observe_edge(url_id, target_id, RelationType.LED_TO, w, at)

            elif event.type == EventType.SEARCH:
                query = (event.data.get("query") or event.content or "").strip()
                if query:
                    query_id = (
                        await self._graph.upsert_node(
                            NodeType.QUERY, query.lower(), query, weight_delta=w
                        )
                    ).id
                    await self._graph.observe_edge(
                        user_id, query_id, RelationType.SEARCHED, w, at
                    )
                    await self._attach_topics(query_id, query, at)
                    if url_id:
                        await self._graph.observe_edge(
                            query_id, url_id, RelationType.LED_TO, w, at
                        )

            elif event.type == EventType.LLM_CHAT:
                model = event.data.get("model", "unknown-llm")
                llm_id = (
                    await self._graph.upsert_node(NodeType.LLM, model, model, weight_delta=w)
                ).id
                await self._graph.observe_edge(user_id, llm_id, RelationType.CHATTED_WITH, w, at)
                await self._attach_topics(llm_id, event.content, at)

            elif event.type == EventType.CONTENT_CREATE:
                key = event.url or hashlib.md5((event.content or "").encode()).hexdigest()
                doc_id = (
                    await self._graph.upsert_node(
                        NodeType.DOCUMENT, key, event.title or "document", weight_delta=w
                    )
                ).id
                await self._graph.observe_edge(user_id, doc_id, RelationType.CREATED, w, at)
                await self._attach_topics(doc_id, f"{event.title}\n{event.content}", at)

            elif event.type == EventType.OPINION:
                text = (event.content or "").strip()
                if text:
                    key = hashlib.md5(text.lower().encode()).hexdigest()[:16]
                    op_id = (
                        await self._graph.upsert_node(
                            NodeType.OPINION, key, text, weight_delta=w,
                            attributes={"text": text, "last_seen": at.isoformat()},
                        )
                    ).id
                    await self._graph.observe_edge(user_id, op_id, RelationType.HOLDS, w, at)
                    await self._attach_topics(op_id, text, at)

            stats[event.type.value] += 1
            if event.session_id and url_id:
                sessions[event.session_id].append((at, url_id))

        await self._build_traces(sessions)
        return dict(stats)

    async def _build_traces(self, sessions: dict[str, list[tuple[datetime, str]]]) -> None:
        for session_id, items in sessions.items():
            if len(items) < 2:
                continue
            items.sort(key=lambda x: x[0])
            node_ids = [nid for _, nid in items]
            await self._graph.add_trace(
                Trace(
                    session_id=session_id,
                    node_ids=node_ids,
                    started_at=items[0][0],
                    ended_at=items[-1][0],
                )
            )

    async def build_profile(self, event_count: int) -> Profile:
        """Roll the current graph state into a human/LLM-readable profile."""
        topics = await self._graph.top_nodes(NodeType.TOPIC, limit=15)
        domains = await self._graph.top_nodes(NodeType.DOMAIN, limit=10)
        opinions = await self._graph.top_nodes(NodeType.OPINION, limit=10)

        interests = [Interest(topic=n.label, weight=round(n.weight, 3)) for n in topics]
        top_domains = [Interest(topic=n.label, weight=round(n.weight, 3)) for n in domains]
        recurring_opinions = [
            Opinion(
                text=n.attributes.get("text", n.label),
                weight=round(n.weight, 3),
                last_seen=n.updated_at,
            )
            for n in opinions
        ]

        behavior_types = await self._behavior_types()
        decision_patterns = await self._decision_patterns()

        summary = self._summarize(interests, top_domains, behavior_types)
        return Profile(
            event_count=event_count,
            interests=interests,
            top_domains=top_domains,
            behavior_types=behavior_types,
            decision_patterns=decision_patterns,
            recurring_opinions=recurring_opinions,
            summary=summary,
        )

    async def _behavior_types(self) -> dict[str, float]:
        # Derive archetype weights from how strongly the user connects to each
        # relation kind, using top edges from the user node.
        user_id = await self._user()
        neighbors = await self._graph.neighbors(user_id, limit=500)
        rel_weight: Counter[RelationType] = Counter()
        for edge, _ in neighbors:
            rel_weight[edge.relation] += edge.effective_weight or 0.0
        rel_to_behavior = {
            RelationType.SEARCHED: "researcher",
            RelationType.VISITED: "researcher",
            RelationType.CHATTED_WITH: "conversationalist",
            RelationType.CREATED: "creator",
            RelationType.HOLDS: "opinionated",
            RelationType.INTERESTED_IN: "researcher",
        }
        scores: Counter[str] = Counter()
        for rel, weight in rel_weight.items():
            scores[rel_to_behavior.get(rel, "navigator")] += weight
        total = sum(scores.values())
        if total <= 0:
            return {}
        return {k: round(v / total, 3) for k, v in scores.most_common()}

    async def _decision_patterns(self) -> list[str]:
        patterns: list[str] = []
        # search -> visit funnel: do queries lead to URL visits?
        queries = await self._graph.top_nodes(NodeType.QUERY, limit=20)
        funnels = 0
        for q in queries:
            led = await self._graph.neighbors(q.id, RelationType.LED_TO, limit=5)
            if led:
                funnels += 1
        if funnels:
            patterns.append(
                f"Researches before deciding: {funnels} searches led to specific pages."
            )
        traces = await self._graph.recent_traces(limit=10)
        multi = [t for t in traces if len(t.node_ids) >= 3]
        if multi:
            patterns.append(
                f"Explores in depth: {len(multi)} sessions spanned 3+ pages of link-following."
            )
        return patterns

    @staticmethod
    def _summarize(
        interests: list[Interest],
        domains: list[Interest],
        behavior: dict[str, float],
    ) -> str:
        top_interests = ", ".join(i.topic for i in interests[:5]) or "n/a"
        top_domains = ", ".join(d.topic for d in domains[:3]) or "n/a"
        archetype = max(behavior, key=behavior.get) if behavior else "unknown"
        return (
            f"Primary online archetype: {archetype}. "
            f"Top interests: {top_interests}. "
            f"Frequent sources: {top_domains}."
        )
