"""Async data-access helpers over the Web API's SQLite DB."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from web_api import db
from web_api.security import GeneratedKey, hash_key


async def upsert_user(
    engine: AsyncEngine,
    google_sub: str,
    email: str | None,
    name: str | None,
    picture: str | None,
) -> str:
    now = db.utcnow_iso()
    async with engine.begin() as conn:
        existing = (
            await conn.execute(
                sa.select(db.users_table).where(db.users_table.c.google_sub == google_sub)
            )
        ).first()
        if existing is not None:
            user_id = existing._mapping["id"]
            await conn.execute(
                db.users_table.update()
                .where(db.users_table.c.id == user_id)
                .values(email=email, name=name, picture=picture, last_login=now)
            )
            return user_id
        user_id = uuid.uuid4().hex
        await conn.execute(
            db.users_table.insert().values(
                id=user_id,
                google_sub=google_sub,
                email=email,
                name=name,
                picture=picture,
                created_at=now,
                last_login=now,
            )
        )
        return user_id


async def get_user(engine: AsyncEngine, user_id: str) -> dict[str, Any] | None:
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                sa.select(db.users_table).where(db.users_table.c.id == user_id)
            )
        ).first()
    return dict(row._mapping) if row else None


async def create_api_key(
    engine: AsyncEngine, user_id: str, name: str, generated: GeneratedKey
) -> dict[str, Any]:
    key_id = uuid.uuid4().hex
    now = db.utcnow_iso()
    async with engine.begin() as conn:
        await conn.execute(
            db.api_keys_table.insert().values(
                id=key_id,
                user_id=user_id,
                name=name,
                prefix=generated.prefix,
                key_hash=generated.key_hash,
                created_at=now,
                last_used=None,
                revoked=False,
                revoked_at=None,
            )
        )
    return {
        "id": key_id,
        "name": name,
        "prefix": generated.prefix,
        "created_at": now,
        "last_used": None,
        "revoked": False,
    }


async def list_api_keys(engine: AsyncEngine, user_id: str) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                sa.select(db.api_keys_table)
                .where(db.api_keys_table.c.user_id == user_id)
                .order_by(db.api_keys_table.c.created_at.desc())
            )
        ).mappings().all()
    return [
        {
            "id": m["id"],
            "name": m["name"],
            "prefix": m["prefix"],
            "created_at": m["created_at"],
            "last_used": m["last_used"],
            "revoked": bool(m["revoked"]),
        }
        for m in rows
    ]


async def revoke_api_key(engine: AsyncEngine, user_id: str, key_id: str) -> bool:
    now = db.utcnow_iso()
    async with engine.begin() as conn:
        result = await conn.execute(
            db.api_keys_table.update()
            .where(
                db.api_keys_table.c.id == key_id,
                db.api_keys_table.c.user_id == user_id,
            )
            .values(revoked=True, revoked_at=now)
        )
    return result.rowcount > 0


async def touch_api_key(engine: AsyncEngine, key_plaintext: str) -> None:
    """Mark a key as used (by hash). Best-effort; used by future brain auth."""
    async with engine.begin() as conn:
        await conn.execute(
            db.api_keys_table.update()
            .where(db.api_keys_table.c.key_hash == hash_key(key_plaintext))
            .values(last_used=db.utcnow_iso())
        )
