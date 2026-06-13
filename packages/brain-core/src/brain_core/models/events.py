"""Raw behavioral events — the append-only input to the brain.

A single ``RawEvent`` model covers every event type via a typed envelope plus
a flexible ``data`` payload. This keeps ingestion validation strict on the
shared fields while allowing each event type to carry its own extras. Helper
accessors keep downstream code from reaching into ``data`` blindly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    VISIT = "visit"
    CLICK = "click"
    DWELL = "dwell"
    LINK = "link"
    SEARCH = "search"
    LLM_CHAT = "llm_chat"
    CONTENT_CREATE = "content_create"
    OPINION = "opinion"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RawEvent(BaseModel):
    """One captured signal of online behavior."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    type: EventType
    timestamp: datetime = Field(default_factory=_utcnow)
    source: str = "unknown"  # e.g. "browser-extension", "mcp", "cursor"
    session_id: str | None = None

    url: str | None = None
    title: str | None = None
    # Free-text content: page text, selection, chat message, opinion, etc.
    content: str | None = None
    # Type-specific extras (e.g. {"query": "..."}, {"dwell_ms": 1234},
    # {"target_url": "..."}, {"model": "gpt-4o", "role": "user"}).
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def _ensure_tz(cls, v: datetime) -> datetime:
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)

    @property
    def domain(self) -> str | None:
        if not self.url:
            return None
        try:
            netloc = urlparse(self.url).netloc.lower()
        except ValueError:
            return None
        return netloc[4:] if netloc.startswith("www.") else netloc or None

    def text_for_memory(self) -> str:
        """Concatenated text used for semantic (vector) memory."""
        parts = [self.title, self.content, self.data.get("query")]
        return "\n".join(str(p) for p in parts if p).strip()


class EventBatch(BaseModel):
    """A batch of events POSTed by a collector (browser extension, etc.)."""

    client: str = "unknown"
    client_version: str | None = None
    events: list[RawEvent] = Field(default_factory=list)
