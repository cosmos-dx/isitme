"""Lightweight keyword/topic extraction.

A deliberately simple, dependency-free extractor: tokenize, drop stopwords and
very short tokens, score by sublinear term frequency, and return the top-N. It
is real and useful for building the graph offline.

TODO(ml): swap for a proper keyphrase/NER/embedding-cluster topic model behind
this same ``extract_topics`` interface for higher-quality topics.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.-]{1,}")

_STOPWORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "any", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his", "how",
    "man", "new", "now", "old", "see", "two", "way", "who", "boy", "did", "its",
    "let", "put", "say", "she", "too", "use", "with", "this", "that", "from",
    "they", "have", "what", "your", "when", "will", "there", "their", "would",
    "about", "which", "into", "than", "then", "them", "these", "some", "more",
    "http", "https", "www", "com", "org", "net", "html", "page", "click", "here",
    "home", "search", "results", "result", "login", "sign", "menu", "back",
}


def extract_topics(text: str | None, max_n: int = 8) -> list[str]:
    if not text:
        return []
    tokens = [t.lower() for t in _TOKEN_RE.findall(text)]
    counts: Counter[str] = Counter()
    for tok in tokens:
        if len(tok) < 3 or tok in _STOPWORDS or tok.isdigit():
            continue
        counts[tok] += 1
    if not counts:
        return []
    scored = sorted(
        counts.items(), key=lambda kv: (math.log1p(kv[1]), kv[0]), reverse=True
    )
    return [tok for tok, _ in scored[:max_n]]
