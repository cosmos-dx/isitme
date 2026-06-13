"""Redaction engine — the privacy gate every event passes through.

Redaction is applied to an event's ``title``, ``content``, ``url`` and string
values inside ``data`` *before* the event is persisted or embedded. It also
enforces per-site rules:

* ``deny_sites``      — event is dropped entirely (never stored).
* ``content_blocklist_sites`` — content/title scrubbed, metadata kept.
* ``allow_sites``     — if non-empty, only these domains are captured.

Detectors cover passwords, banking, health, secrets/API-keys and generic PII
(emails, phones, credit cards, SSNs), plus user-supplied custom regexes. The
same rules ship to the browser extension so redaction also happens client-side.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fnmatch import fnmatch

from brain_core.config import RedactionSettings
from brain_core.models.events import RawEvent

# Built-in detectors keyed by category. Patterns are intentionally conservative
# (favor over-redaction of sensitive data over leaking it).
_BUILTIN: dict[str, list[re.Pattern[str]]] = {
    "pii": [
        re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
        re.compile(r"\b(?:\+?\d[\d\s().-]{7,}\d)\b"),  # phone
        re.compile(r"\b(?:\d[ -]?){13,16}\b"),  # credit-card-ish
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # US SSN
    ],
    "secrets": [
        re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),  # OpenAI-style key
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),  # GitHub token
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"(?i)\b(?:api[_-]?key|secret|token|bearer)\b\s*[:=]\s*\S+"),
    ],
    "banking": [
        re.compile(r"(?i)\b(?:iban)\b\s*[:=]?\s*[A-Z]{2}\d{2}[A-Z0-9]{10,30}"),
        re.compile(r"(?i)\b(?:routing|account)\s*(?:no|number|#)?\s*[:=]?\s*\d{6,17}"),
        re.compile(r"(?i)\bcvv\b\s*[:=]?\s*\d{3,4}"),
    ],
    "passwords": [
        re.compile(r"(?i)\b(?:password|passwd|pwd|passphrase)\b\s*[:=]\s*\S+"),
    ],
    "health": [
        re.compile(
            r"(?i)\b(?:diagnos\w+|prescri\w+|mg/dl|blood pressure|"
            r"medical record|patient id)\b[:=\s][^\n]{0,40}"
        ),
    ],
}


@dataclass
class RedactionResult:
    event: RawEvent | None  # None => dropped entirely
    dropped: bool = False
    redaction_count: int = 0
    categories_hit: list[str] = field(default_factory=list)


class RedactionEngine:
    def __init__(self, settings: RedactionSettings):
        self._settings = settings
        self._custom = [
            (cp.name, re.compile(cp.pattern)) for cp in settings.custom_patterns
        ]

    def _active_patterns(self) -> list[tuple[str, re.Pattern[str]]]:
        patterns: list[tuple[str, re.Pattern[str]]] = []
        for category, enabled in self._settings.categories.items():
            if enabled:
                for pat in _BUILTIN.get(category, []):
                    patterns.append((category, pat))
        patterns.extend((f"custom:{name}", pat) for name, pat in self._custom)
        return patterns

    @staticmethod
    def _site_matches(domain: str | None, patterns: list[str]) -> bool:
        if not domain:
            return False
        return any(fnmatch(domain, p) for p in patterns)

    def _scrub(self, text: str | None, hits: set[str]) -> tuple[str | None, int]:
        if not text:
            return text, 0
        count = 0
        out = text
        for category, pattern in self._active_patterns():
            new_out, n = pattern.subn(self._settings.replacement, out)
            if n:
                count += n
                hits.add(category)
                out = new_out
        return out, count

    def apply(self, event: RawEvent) -> RedactionResult:
        """Redact a single event in place (returns a new, scrubbed event)."""
        if not self._settings.enabled:
            return RedactionResult(event=event)

        domain = event.domain
        if self._site_matches(domain, self._settings.content_blocklist_sites):
            scrubbed = event.model_copy(update={"content": None, "title": None})
            return RedactionResult(event=scrubbed, redaction_count=1, categories_hit=["site"])

        hits: set[str] = set()
        total = 0
        title, n = self._scrub(event.title, hits)
        total += n
        content, n = self._scrub(event.content, hits)
        total += n
        url, n = self._scrub(event.url, hits)
        total += n

        new_data = dict(event.data)
        for k, v in list(new_data.items()):
            if isinstance(v, str):
                new_data[k], n = self._scrub(v, hits)
                total += n

        scrubbed = event.model_copy(
            update={"title": title, "content": content, "url": url, "data": new_data}
        )
        return RedactionResult(
            event=scrubbed, redaction_count=total, categories_hit=sorted(hits)
        )
