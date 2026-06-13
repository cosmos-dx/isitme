"""Optional Chroma-backed ``VectorStore``.

Requires ``pip install 'brain-core[chroma]'``. Provided as a persistent local
alternative to the numpy default. Imports are lazy so the dependency is only
needed when ``vector_backend=chroma``.
"""

from __future__ import annotations

from brain_core.storage.base import VectorStore


class ChromaVectorStore(VectorStore):
    def __init__(self, path: str, collection: str = "brain_memory"):
        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover - optional path
            raise ImportError(
                "chromadb not installed. Install with: pip install 'brain-core[chroma]'"
            ) from exc
        self._client = chromadb.PersistentClient(path=path)
        self._collection_name = collection
        self._collection = None

    async def init(self, dim: int) -> None:
        self._collection = self._client.get_or_create_collection(
            self._collection_name, metadata={"hnsw:space": "cosine"}
        )

    async def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        texts: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas
        )

    async def query(
        self, embedding: list[float], k: int = 5
    ) -> list[tuple[str, float, str, dict]]:
        res = self._collection.query(query_embeddings=[embedding], n_results=k)
        out: list[tuple[str, float, str, dict]] = []
        ids = res.get("ids", [[]])[0]
        dists = res.get("distances", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        for _id, dist, doc, meta in zip(ids, dists, docs, metas, strict=False):
            out.append((_id, 1.0 - float(dist), doc, meta or {}))
        return out

    async def count(self) -> int:
        return self._collection.count() if self._collection else 0

    async def close(self) -> None:
        return None
