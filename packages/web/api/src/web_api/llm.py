"""Optional OpenAI enrichment.

The brain's ``/v1/ask`` already returns a templated answer plus retrieved
sources. When an ``OPENAI_API_KEY`` is configured (and the ``openai`` package is
installed) we synthesize a more natural answer over those sources. Everything
degrades gracefully to the brain's template if OpenAI is unavailable.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("web.llm")


class LLMHelper:
    def __init__(self, api_key: str | None, model: str = "gpt-4o-mini") -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any | None = None
        if api_key:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=api_key)
            except Exception as exc:  # pragma: no cover - import/runtime guard
                logger.warning("OpenAI unavailable, falling back to template: %s", exc)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def synthesize_answer(
        self, question: str, sources: list[dict[str, Any]], profile_summary: str
    ) -> str | None:
        if not self._client:
            return None
        context = "\n".join(f"- {s.get('text', '')[:400]}" for s in sources[:8])
        prompt = (
            "You are the user's portable 'online brain'. Answer in their voice, "
            "grounded ONLY in the retrieved memories below. Be concise and concrete; "
            "if the memories are thin, say so honestly.\n\n"
            f"User profile: {profile_summary or 'n/a'}\n\n"
            f"Question: {question}\n\n"
            f"Retrieved memories:\n{context or '(none)'}"
        )
        try:
            resp = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=400,
            )
            return (resp.choices[0].message.content or "").strip() or None
        except Exception as exc:  # pragma: no cover - network/runtime guard
            logger.warning("OpenAI synthesis failed, falling back to template: %s", exc)
            return None
