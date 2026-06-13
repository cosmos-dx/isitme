"""Configuration for the Web API / BFF.

Secrets are read from the repo-root ``.env`` (gitignored) — never hardcoded:

* ``OAUTH_CLIENT_JSON`` — Google OAuth *web* client JSON. We honor its pinned
  ``redirect_uris`` and ``javascript_origins`` exactly (Google rejects mismatches).
* ``OPENAI_API_KEY``    — optional; used to enrich the "ask your brain" answer.

Non-secret knobs (ports, brain endpoint) have safe localhost defaults and can be
overridden with ``WEB_`` env vars.
"""

from __future__ import annotations

import json
import os
import secrets
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward from this file until a directory containing ``.git`` is found."""
    here = (start or Path(__file__).resolve()).parent
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate
    # Fallback: packages/web/api/src/web_api/config.py -> repo root is parents[5].
    return Path(__file__).resolve().parents[5]


class GoogleOAuthConfig:
    """Parsed Google OAuth web-client config."""

    def __init__(self, raw: dict) -> None:
        web = raw.get("web") or raw.get("installed") or raw
        self.client_id: str = web["client_id"]
        self.client_secret: str = web["client_secret"]
        self.auth_uri: str = web.get("auth_uri", "https://accounts.google.com/o/oauth2/auth")
        self.token_uri: str = web.get("token_uri", "https://oauth2.googleapis.com/token")
        self.redirect_uris: list[str] = web.get("redirect_uris", [])
        self.javascript_origins: list[str] = web.get("javascript_origins", [])

    @property
    def redirect_uri(self) -> str:
        if not self.redirect_uris:
            raise RuntimeError("OAUTH_CLIENT_JSON has no redirect_uris")
        return self.redirect_uris[0]

    @property
    def frontend_origin(self) -> str:
        if self.javascript_origins:
            return self.javascript_origins[0]
        return "http://localhost:4000"


class Settings:
    def __init__(self) -> None:
        self.repo_root = find_repo_root()
        load_dotenv(self.repo_root / ".env")

        raw = os.environ.get("OAUTH_CLIENT_JSON")
        self.google: GoogleOAuthConfig | None = None
        if raw:
            try:
                self.google = GoogleOAuthConfig(json.loads(raw))
            except (json.JSONDecodeError, KeyError) as exc:  # pragma: no cover
                raise RuntimeError(f"OAUTH_CLIENT_JSON is malformed: {exc}") from exc

        self.openai_api_key: str | None = os.environ.get("OPENAI_API_KEY") or None

        # Non-secret, overridable knobs.
        self.host: str = os.environ.get("WEB_HOST", "127.0.0.1")
        self.port: int = int(os.environ.get("WEB_PORT", "5050"))
        self.brain_base_url: str = os.environ.get(
            "WEB_BRAIN_BASE_URL", "http://127.0.0.1:8077"
        ).rstrip("/")
        # The endpoint the extension / MCP clients should hit. Defaults to brain.
        self.brain_public_url: str = os.environ.get(
            "WEB_BRAIN_PUBLIC_URL", self.brain_base_url
        ).rstrip("/")

        self.frontend_origin: str = os.environ.get(
            "WEB_FRONTEND_ORIGIN",
            self.google.frontend_origin if self.google else "http://localhost:4000",
        ).rstrip("/")

        # Local state (gitignored): sqlite db + persisted session secret.
        self.data_dir: Path = Path(
            os.environ.get("WEB_DATA_DIR", str(self.repo_root / ".brain" / "web"))
        )
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_url: str = f"sqlite+aiosqlite:///{self.data_dir / 'web.db'}"

        # Optional MongoDB persistence. Unset -> SQLite (zero setup). When
        # WEB_MONGO_URI is provided, users/api_keys/usage live in Mongo instead.
        self.mongo_uri: str | None = os.environ.get("WEB_MONGO_URI") or None
        self.mongo_db: str = os.environ.get("WEB_MONGO_DB", "isitme")

        self.session_secret: str = self._resolve_session_secret()
        self.session_cookie: str = os.environ.get("WEB_SESSION_COOKIE", "isitme_session")

    def _resolve_session_secret(self) -> str:
        env_secret = os.environ.get("WEB_SESSION_SECRET")
        if env_secret:
            return env_secret
        key_file = self.data_dir / "session_secret.key"
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        secret = secrets.token_urlsafe(48)
        key_file.write_text(secret, encoding="utf-8")
        try:
            key_file.chmod(0o600)
        except OSError:  # pragma: no cover - best effort on some filesystems
            pass
        return secret

    @property
    def oauth_configured(self) -> bool:
        return self.google is not None

    @property
    def dashboard_url(self) -> str:
        return f"{self.frontend_origin}/dashboard"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
