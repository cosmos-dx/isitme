"""Derived user profile — the human-readable rollup of the brain.

Produced by the insight engine from the event stream + knowledge graph. This
is what ``get_profile`` returns and what an LLM consumes to "become" the user.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Interest(BaseModel):
    topic: str
    weight: float


class Opinion(BaseModel):
    text: str
    weight: float
    last_seen: datetime


class Profile(BaseModel):
    generated_at: datetime = Field(default_factory=_utcnow)
    event_count: int = 0

    interests: list[Interest] = Field(default_factory=list)
    top_domains: list[Interest] = Field(default_factory=list)
    # e.g. {"researcher": 0.4, "shopper": 0.1, "conversationalist": 0.3}
    behavior_types: dict[str, float] = Field(default_factory=dict)
    # Human-readable patterns, e.g. "Often searches then reads docs before deciding".
    decision_patterns: list[str] = Field(default_factory=list)
    recurring_opinions: list[Opinion] = Field(default_factory=list)

    summary: str = ""
