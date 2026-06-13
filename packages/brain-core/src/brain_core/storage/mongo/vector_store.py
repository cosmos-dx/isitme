"""MongoDB implementation of :class:`VectorStore` (collection ``vectors``).

Embeddings are stored as plain float arrays in the document field
``embedding``. Similarity search is performed in-process with numpy cosine
(brute-force kNN) — exact and dependency-light, identical in behavior to the
default numpy backend.

Scaling to native vector search
-------------------------------
On MongoDB Atlas you can replace :meth:`query` with a ``$vectorSearch``
aggregation backed by an Atlas Vector Search index, e.g.::

    await self._coll.aggregate([
        {"$vectorSearch": {
            "index": "vector_index",
            "path": "embedding",
            "queryVector": embedding,
            "numCandidates": 100,
            "limit": k,
        }},
        {"$project": {"text": 1, "metadata": 1,
                      "score": {"$meta": "vectorSearchScore"}}},
    ])

Create the index once (Atlas UI or ``createSearchIndex``) over ``embedding``
with ``"numDimensions": dim`` and ``"similarity": "cosine"``. The brute-force
path below stays correct for local / self-hosted Mongo without that feature.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from brain_core.storage.base import VectorStore
from brain_core.storage.mongo import make_motor_client


class MongoVectorStore(VectorStore):
    def __init__(self, uri: str, db_name: str, client: Any | None = None):
        self._uri = uri
        self._db_name = db_name
        self._client = client
        self._db: Any | None = None
        self._dim = 0

    @property
    def _coll(self) -> Any:
        return self._db["vectors"]

    async def init(self, dim: int) -> None:
        self._dim = dim
        if self._client is None:
            self._client = make_motor_client(self._uri)
        self._db = self._client[self._db_name]

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        # Upsert keyed on id (mirrors the chroma backend's upsert semantics).
        for _id, emb, text, meta in zip(ids, embeddings, texts, metadatas, strict=False):
            await self._coll.replace_one(
                {"_id": _id},
                {"_id": _id, "embedding": list(emb), "text": text, "metadata": meta},
                upsert=True,
            )

    async def query(
        self, embedding: list[float], k: int = 5
    ) -> list[tuple[str, float, str, dict]]:
        docs = [
            doc
            async for doc in self._coll.find(
                {}, {"embedding": 1, "text": 1, "metadata": 1}
            )
        ]
        if not docs:
            return []
        matrix = np.asarray([doc["embedding"] for doc in docs], dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms
        q = np.asarray(embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm != 0:
            q = q / q_norm
        scores = matrix @ q
        k = min(k, len(docs))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [
            (
                docs[i]["_id"],
                float(scores[i]),
                docs[i].get("text", ""),
                docs[i].get("metadata") or {},
            )
            for i in top
        ]

    async def count(self) -> int:
        return int(await self._coll.count_documents({}))

    async def close(self) -> None:
        if self._client is not None:
            self._client.close()
