"""At-rest encryption for synced payloads.

Uses Fernet (AES-128-CBC + HMAC) from ``cryptography``. If no key is configured
and sync is enabled, an ephemeral key is generated and stored under ``data_dir``
(printed once) so the user can persist it. Local-only mode never encrypts
because nothing leaves the machine.
"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet


class PayloadCipher:
    def __init__(self, key: str):
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, payload: dict) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(raw).decode("ascii")

    def decrypt(self, token: str) -> dict:
        return json.loads(self._fernet.decrypt(token.encode("ascii")))


def load_or_create_key(configured_key: str | None, data_dir: Path) -> str:
    if configured_key:
        return configured_key
    key_file = data_dir / "sync.key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = Fernet.generate_key().decode("ascii")
    key_file.write_text(key)
    print(
        f"[isitme] Generated sync encryption key at {key_file} — "
        "back this up; without it synced data cannot be decrypted."
    )
    return key
