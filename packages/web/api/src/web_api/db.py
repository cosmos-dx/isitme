"""SQLAlchemy Core schema + async engine for the Web API's small SQLite DB.

Stores users (from Google OAuth), API keys (only a *hash* of the key is kept),
and lightweight usage timestamps. Mirrors the brain-core convention of storing
timestamps as ISO-8601 TEXT for deterministic timezone handling.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

metadata = sa.MetaData()

users_table = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("google_sub", sa.String, nullable=False, unique=True, index=True),
    sa.Column("email", sa.String, nullable=True),
    sa.Column("name", sa.String, nullable=True),
    sa.Column("picture", sa.String, nullable=True),
    sa.Column("created_at", sa.String, nullable=False),
    sa.Column("last_login", sa.String, nullable=True),
)

api_keys_table = sa.Table(
    "api_keys",
    metadata,
    sa.Column("id", sa.String, primary_key=True),
    sa.Column("user_id", sa.String, nullable=False, index=True),
    sa.Column("name", sa.String, nullable=False),
    sa.Column("prefix", sa.String, nullable=False),
    sa.Column("key_hash", sa.String, nullable=False, index=True),
    sa.Column("created_at", sa.String, nullable=False),
    sa.Column("last_used", sa.String, nullable=True),
    sa.Column("revoked", sa.Boolean, nullable=False, default=False),
    sa.Column("revoked_at", sa.String, nullable=True),
)

usage_table = sa.Table(
    "usage",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.String, nullable=False, index=True),
    sa.Column("endpoint", sa.String, nullable=False),
    sa.Column("at", sa.String, nullable=False),
)


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, future=True)


async def create_all(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def utcnow_iso() -> str:
    return iso(datetime.now(timezone.utc))
