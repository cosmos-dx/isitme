"""Deterministic hashing embeddings — zero dependencies, zero network.

A classic feature-hashing ("hashing trick") bag-of-words model: each token is
hashed into a bucket of a fixed-dim vector with a sign, weighted by sublinear
term frequency, then L2-normalized. It is not semantically deep, but it is
stable, fast, and lets the entire system run offline out of the box. Swap to a
real embedding model via config when quality matters.
"""

from __future__ import annotations

import hashlib
import math
import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class HashingEmbeddingProvider:
    def __init__(self, dim: int = 256):
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def _embed_sync(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        tokens = _TOKEN_RE.findall((text or "").lower())
        if not tokens:
            return vec
        counts: dict[str, int] = {}
        for tok in tokens:
            counts[tok] = counts.get(tok, 0) + 1
        for tok, count in counts.items():
            digest = hashlib.md5(tok.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_sync(t) for t in texts]

    async def embed_one(self, text: str) -> list[float]:
        return self._embed_sync(text)
