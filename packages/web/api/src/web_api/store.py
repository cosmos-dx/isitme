"""Persistence abstraction for the Web API (users, API keys, usage).

Two interchangeable backends sit behind the :class:`WebStore` ABC:

* :class:`SqliteWebStore` — the zero-setup default (SQLAlchemy async + SQLite).
* :class:`MongoWebStore` — opt-in, enabled when ``WEB_MONGO_URI`` is set
  (collections ``users``, ``api_keys``, ``usage``; uses the async ``motor``
  driver).

API keys are NEVER stored or logged in plaintext: only the SHA-256 hash, a
short non-secret prefix, the label, the owner, timestamps and a revoked flag
are persisted.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from web_api import db
from web_api.security import GeneratedKey, hash_key


class WebStore(ABC):
    """Backend-agnostic data access for users, API keys and usage."""

    @abstractmethod
    async def init(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    async def upsert_user(
        self,
        google_sub: str,
        email: str | None,
        name: str | None,
        picture: str | None,
    ) -> str: ...

    @abstractmethod
    async def get_user(self, user_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def create_api_key(
        self, user_id: str, name: str, generated: GeneratedKey
    ) -> dict[str, Any]: ...

    @abstractmethod
    async def list_api_keys(self, user_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def revoke_api_key(self, user_id: str, key_id: str) -> bool: ...

    @abstractmethod
    async def authenticate_key(self, plaintext: str) -> dict[str, Any] | None:
        """Resolve the owning user for a valid, non-revoked key (by hash).

        Updates ``last_used`` as a side effect. Returns ``None`` for unknown or
        revoked keys. The plaintext is hashed locally and never stored/logged.
        """

    @abstractmethod
    async def record_usage(self, user_id: str, endpoint: str) -> None: ...


class SqliteWebStore(WebStore):
    """SQLAlchemy-async SQLite backend (default; also works on Postgres DSNs)."""

    def __init__(self, url: str):
        self._url = url
        self._engine: AsyncEngine | None = None

    @property
    def engine(self) -> AsyncEngine:
        assert self._engine is not None, "store not initialized"
        return self._engine

    async def init(self) -> None:
        self._engine = db.make_engine(self._url)
        await db.create_all(self._engine)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    async def upsert_user(
        self,
        google_sub: str,
        email: str | None,
        name: str | None,
        picture: str | None,
    ) -> str:
        now = db.utcnow_iso()
        async with self.engine.begin() as conn:
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

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        async with self.engine.connect() as conn:
            row = (
                await conn.execute(
                    sa.select(db.users_table).where(db.users_table.c.id == user_id)
                )
            ).first()
        return dict(row._mapping) if row else None

    async def create_api_key(
        self, user_id: str, name: str, generated: GeneratedKey
    ) -> dict[str, Any]:
        key_id = uuid.uuid4().hex
        now = db.utcnow_iso()
        async with self.engine.begin() as conn:
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

    async def list_api_keys(self, user_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
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

    async def revoke_api_key(self, user_id: str, key_id: str) -> bool:
        now = db.utcnow_iso()
        async with self.engine.begin() as conn:
            result = await conn.execute(
                db.api_keys_table.update()
                .where(
                    db.api_keys_table.c.id == key_id,
                    db.api_keys_table.c.user_id == user_id,
                )
                .values(revoked=True, revoked_at=now)
            )
        return result.rowcount > 0

    async def authenticate_key(self, plaintext: str) -> dict[str, Any] | None:
        key_hash = hash_key(plaintext)
        now = db.utcnow_iso()
        async with self.engine.begin() as conn:
            row = (
                await conn.execute(
                    sa.select(db.api_keys_table).where(
                        db.api_keys_table.c.key_hash == key_hash,
                        db.api_keys_table.c.revoked == False,  # noqa: E712
                    )
                )
            ).first()
            if row is None:
                return None
            user_id = row._mapping["user_id"]
            await conn.execute(
                db.api_keys_table.update()
                .where(db.api_keys_table.c.id == row._mapping["id"])
                .values(last_used=now)
            )
            user_row = (
                await conn.execute(
                    sa.select(db.users_table).where(db.users_table.c.id == user_id)
                )
            ).first()
        return dict(user_row._mapping) if user_row else None

    async def record_usage(self, user_id: str, endpoint: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                db.usage_table.insert().values(
                    user_id=user_id, endpoint=endpoint, at=db.utcnow_iso()
                )
            )


class MongoWebStore(WebStore):
    """MongoDB backend (opt-in via ``WEB_MONGO_URI``) using ``motor``."""

    def __init__(self, uri: str, db_name: str, client: Any | None = None):
        self._uri = uri
        self._db_name = db_name
        self._client = client
        self._db: Any | None = None

    @property
    def _users(self) -> Any:
        return self._db["users"]

    @property
    def _keys(self) -> Any:
        return self._db["api_keys"]

    @property
    def _usage(self) -> Any:
        return self._db["usage"]

    async def init(self) -> None:
        if self._client is None:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
            except ImportError as exc:  # pragma: no cover - optional path
                raise ImportError(
                    "motor not installed. Install with: pip install 'web-api[mongo]'"
                ) from exc
            self._client = AsyncIOMotorClient(self._uri)
        self._db = self._client[self._db_name]
        await self._users.create_index("google_sub", unique=True)
        await self._keys.create_index("key_hash")
        await self._keys.create_index("user_id")
        await self._usage.create_index("user_id")

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()

    async def upsert_user(
        self,
        google_sub: str,
        email: str | None,
        name: str | None,
        picture: str | None,
    ) -> str:
        now = db.utcnow_iso()
        existing = await self._users.find_one({"google_sub": google_sub})
        if existing is not None:
            await self._users.update_one(
                {"_id": existing["_id"]},
                {"$set": {"email": email, "name": name, "picture": picture, "last_login": now}},
            )
            return existing["_id"]
        user_id = uuid.uuid4().hex
        await self._users.insert_one(
            {
                "_id": user_id,
                "google_sub": google_sub,
                "email": email,
                "name": name,
                "picture": picture,
                "created_at": now,
                "last_login": now,
            }
        )
        return user_id

    @staticmethod
    def _user_doc_to_dict(doc: dict[str, Any]) -> dict[str, Any]:
        out = dict(doc)
        out["id"] = out.pop("_id")
        return out

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        doc = await self._users.find_one({"_id": user_id})
        return self._user_doc_to_dict(doc) if doc else None

    async def create_api_key(
        self, user_id: str, name: str, generated: GeneratedKey
    ) -> dict[str, Any]:
        key_id = uuid.uuid4().hex
        now = db.utcnow_iso()
        await self._keys.insert_one(
            {
                "_id": key_id,
                "user_id": user_id,
                "name": name,
                "prefix": generated.prefix,
                "key_hash": generated.key_hash,
                "created_at": now,
                "last_used": None,
                "revoked": False,
                "revoked_at": None,
            }
        )
        return {
            "id": key_id,
            "name": name,
            "prefix": generated.prefix,
            "created_at": now,
            "last_used": None,
            "revoked": False,
        }

    async def list_api_keys(self, user_id: str) -> list[dict[str, Any]]:
        cursor = self._keys.find({"user_id": user_id}).sort("created_at", -1)
        return [
            {
                "id": doc["_id"],
                "name": doc["name"],
                "prefix": doc["prefix"],
                "created_at": doc["created_at"],
                "last_used": doc.get("last_used"),
                "revoked": bool(doc.get("revoked", False)),
            }
            async for doc in cursor
        ]

    async def revoke_api_key(self, user_id: str, key_id: str) -> bool:
        result = await self._keys.update_one(
            {"_id": key_id, "user_id": user_id},
            {"$set": {"revoked": True, "revoked_at": db.utcnow_iso()}},
        )
        return result.modified_count > 0

    async def authenticate_key(self, plaintext: str) -> dict[str, Any] | None:
        key_hash = hash_key(plaintext)
        doc = await self._keys.find_one({"key_hash": key_hash, "revoked": False})
        if doc is None:
            return None
        await self._keys.update_one(
            {"_id": doc["_id"]}, {"$set": {"last_used": db.utcnow_iso()}}
        )
        user = await self._users.find_one({"_id": doc["user_id"]})
        return self._user_doc_to_dict(user) if user else None

    async def record_usage(self, user_id: str, endpoint: str) -> None:
        await self._usage.insert_one(
            {"user_id": user_id, "endpoint": endpoint, "at": db.utcnow_iso()}
        )


def build_store(settings: Any) -> WebStore:
    """Construct the configured store: Mongo when ``mongo_uri`` is set, else SQLite."""
    mongo_uri = getattr(settings, "mongo_uri", None)
    if mongo_uri:
        return MongoWebStore(mongo_uri, settings.mongo_db)
    return SqliteWebStore(settings.db_url)
