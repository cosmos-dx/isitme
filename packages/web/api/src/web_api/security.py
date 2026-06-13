"""API-key generation and hashing.

A key is shown to the user exactly once at creation; we persist only a SHA-256
hash plus a short non-secret prefix (for display / identification).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

KEY_PREFIX = "isme"
_PREFIX_DISPLAY_LEN = 12


@dataclass(frozen=True)
class GeneratedKey:
    plaintext: str
    prefix: str
    key_hash: str


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_api_key() -> GeneratedKey:
    token = secrets.token_urlsafe(32)
    plaintext = f"{KEY_PREFIX}_{token}"
    return GeneratedKey(
        plaintext=plaintext,
        prefix=plaintext[:_PREFIX_DISPLAY_LEN],
        key_hash=hash_key(plaintext),
    )
