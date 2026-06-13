"""Time-decay math for edge/node weights.

Weights model recency-biased importance via exponential decay with a
configurable half-life. The *raw* weight stored alongside ``last_seen`` is the
effective weight at the moment it was last observed; reading it later decays it
to "now". Observing an edge again decays the old value to the observation time
and adds the new increment, so frequently-revisited relations stay strong while
stale ones fade.
"""

from __future__ import annotations

from datetime import datetime, timezone

_LN2 = 0.6931471805599453


def decay_factor(elapsed_days: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    if elapsed_days <= 0:
        return 1.0
    return 0.5 ** (elapsed_days / half_life_days)


def effective_weight(
    weight: float, last_seen: datetime, now: datetime, half_life_days: float
) -> float:
    elapsed = (now - last_seen).total_seconds() / 86400.0
    return weight * decay_factor(elapsed, half_life_days)


def reinforce(
    prev_weight: float,
    last_seen: datetime,
    delta: float,
    now: datetime,
    half_life_days: float,
) -> float:
    """New raw weight after decaying the prior to ``now`` and adding ``delta``."""
    return effective_weight(prev_weight, last_seen, now, half_life_days) + delta


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
