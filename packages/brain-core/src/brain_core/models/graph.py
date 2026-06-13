"""Knowledge-graph primitives: typed nodes, weighted/decaying edges, traces.

The "online brain" is a directed multigraph:

* **Nodes** are typed entities (the user, domains, URLs, topics, queries,
  LLMs, opinions, documents, people).
* **Edges** are typed relations carrying a *raw weight* plus a *last_seen*
  timestamp. The effective weight decays exponentially with time and is
  re-strengthened on each new observation (see ``decay.py``).
* **Traces** are ordered node paths reconstructed from a browsing session.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NodeType(str, Enum):
    USER = "user"
    DOMAIN = "domain"
    URL = "url"
    TOPIC = "topic"
    QUERY = "query"
    LLM = "llm"
    OPINION = "opinion"
    DOCUMENT = "document"
    PERSON = "person"


class RelationType(str, Enum):
    VISITED = "visited"  # user -> domain/url
    CONTAINS = "contains"  # domain -> url
    SEARCHED = "searched"  # user -> query
    LED_TO = "led_to"  # query/url -> url (navigation / link trail)
    ABOUT = "about"  # url/query/chat -> topic
    INTERESTED_IN = "interested_in"  # user -> topic
    CHATTED_WITH = "chatted_with"  # user -> llm
    HOLDS = "holds"  # user -> opinion
    CREATED = "created"  # user -> document
    MENTIONS = "mentions"  # any -> entity/person


class Node(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: NodeType
    # Canonical dedup key within a type (e.g. normalized topic / domain / url).
    key: str
    label: str
    weight: float = 0.0  # cumulative importance (sum of decayed observations)
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class Edge(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    src: str  # Node.id
    dst: str  # Node.id
    relation: RelationType
    weight: float = 0.0  # raw weight at last_seen (pre-decay)
    last_seen: datetime = Field(default_factory=_utcnow)
    created_at: datetime = Field(default_factory=_utcnow)
    attributes: dict[str, Any] = Field(default_factory=dict)
    # Effective (time-decayed) weight, populated by the store on read.
    effective_weight: float | None = None


class Trace(BaseModel):
    """A session reconstructed as an ordered path through the graph."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    session_id: str
    node_ids: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime = Field(default_factory=_utcnow)
    attributes: dict[str, Any] = Field(default_factory=dict)
