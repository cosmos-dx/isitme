"""In-process numpy ``VectorStore`` — the zero-dependency default.

Embeddings are L2-normalized and stored in a single matrix; queries are a dot
product (= cosine similarity). Persisted to a ``.npz`` + JSON sidecar under
``data_dir`` so memory survives restarts. This is intentionally simple and
exact (brute-force kNN); for large corpora swap in Qdrant/Chroma/pgvector
behind the same ``VectorStore`` ABC.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np

from brain_core.storage.base import VectorStore


class NumpyVectorStore(VectorStore):
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._dim = 0
        self._ids: list[str] = []
        self._texts: list[str] = []
        self._metas: list[dict] = []
        self._matrix: np.ndarray | None = None
        self._lock = asyncio.Lock()

    @property
    def _vec_file(self) -> Path:
        return self._path.with_suffix(".npz")

    @property
    def _meta_file(self) -> Path:
        return self._path.with_suffix(".json")

    async def init(self, dim: int) -> None:
        self._dim = dim
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._vec_file.exists() and self._meta_file.exists():
            with np.load(self._vec_file) as data:
                mat = data["matrix"]
            meta = json.loads(self._meta_file.read_text())
            if mat.shape[1] == dim:
                self._matrix = mat
                self._ids = meta["ids"]
                self._texts = meta["texts"]
                self._metas = meta["metas"]

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        new = self._normalize(np.asarray(embeddings, dtype=np.float32))
        async with self._lock:
            self._matrix = new if self._matrix is None else np.vstack([self._matrix, new])
            self._ids.extend(ids)
            self._texts.extend(texts)
            self._metas.extend(metadatas)
            await asyncio.to_thread(self._persist)

    def _persist(self) -> None:
        if self._matrix is None:
            return
        np.savez_compressed(self._vec_file, matrix=self._matrix)
        self._meta_file.write_text(
            json.dumps({"ids": self._ids, "texts": self._texts, "metas": self._metas})
        )

    async def query(
        self, embedding: list[float], k: int = 5
    ) -> list[tuple[str, float, str, dict]]:
        if self._matrix is None or len(self._ids) == 0:
            return []
        q = np.asarray([embedding], dtype=np.float32)
        q = self._normalize(q)[0]
        scores = self._matrix @ q
        k = min(k, len(self._ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [
            (self._ids[i], float(scores[i]), self._texts[i], self._metas[i]) for i in top
        ]

    async def count(self) -> int:
        return len(self._ids)

    async def close(self) -> None:
        async with self._lock:
            await asyncio.to_thread(self._persist)
