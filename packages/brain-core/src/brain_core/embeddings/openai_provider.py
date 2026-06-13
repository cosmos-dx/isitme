"""Optional OpenAI embedding provider.

Requires ``pip install 'brain-core[openai]'`` and an API key (config
``embedding.openai_api_key`` or ``BRAIN_EMBEDDING__OPENAI_API_KEY``). This is
the only provider that touches the network, and it is never the default.
"""

from __future__ import annotations

from brain_core.embeddings.base import EmbeddingProvider

_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str = "text-embedding-3-small", api_key: str | None = None):
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover - optional path
            raise ImportError(
                "openai not installed. Install with: pip install 'brain-core[openai]'"
            ) from exc
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dim = _DIMS.get(model, 1536)

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in resp.data]
