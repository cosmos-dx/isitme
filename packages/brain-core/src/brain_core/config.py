"""Shared configuration for the Core Brain.

Built on ``pydantic-settings``. Resolution order (last wins):

1. Defaults baked into the models below (fully local, zero-network).
2. A YAML file (``BRAIN_CONFIG`` env var, else ``./config.yaml`` if present).
3. Environment variables prefixed ``BRAIN_`` (nested via ``__``).

This same module is imported by ``brain-core`` and the ``brain-mcp`` thin
client so the two stay schema-consistent.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

EventCategory = Literal[
    "visit", "click", "dwell", "link", "search", "llm_chat", "content_create", "opinion"
]


class CaptureSettings(BaseModel):
    categories: dict[str, bool] = Field(
        default_factory=lambda: {
            "visit": True,
            "click": True,
            "dwell": True,
            "link": True,
            "search": True,
            "llm_chat": True,
            "content_create": True,
            "opinion": True,
        }
    )
    capture_page_content: bool = True
    capture_form_inputs: bool = False
    allow_sites: list[str] = Field(default_factory=list)
    deny_sites: list[str] = Field(default_factory=list)
    retention_days: int = 365


class CustomPattern(BaseModel):
    name: str
    pattern: str


class RedactionSettings(BaseModel):
    enabled: bool = True
    categories: dict[str, bool] = Field(
        default_factory=lambda: {
            "passwords": True,
            "banking": True,
            "health": True,
            "secrets": True,
            "pii": True,
        }
    )
    custom_patterns: list[CustomPattern] = Field(default_factory=list)
    content_blocklist_sites: list[str] = Field(default_factory=list)
    replacement: str = "[REDACTED]"


class EmbeddingSettings(BaseModel):
    provider: Literal["hashing", "sentence_transformers", "openai"] = "hashing"
    dim: int = 256
    st_model: str = "all-MiniLM-L6-v2"
    openai_model: str = "text-embedding-3-small"
    openai_api_key: str | None = None


class StorageSettings(BaseModel):
    event_backend: Literal["sqlite", "postgres"] = "sqlite"
    graph_backend: Literal["sqlite", "neo4j", "kuzu"] = "sqlite"
    vector_backend: Literal["numpy", "chroma", "qdrant", "pgvector"] = "numpy"
    postgres_dsn: str | None = None
    chroma_path: str | None = None
    qdrant_url: str | None = None
    neo4j_uri: str | None = None


class GraphSettings(BaseModel):
    edge_half_life_days: float = 30.0
    default_edge_weight: float = 1.0
    max_topics_per_event: int = 8


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8077


class CloudSettings(BaseModel):
    endpoint: str | None = None
    api_key: str | None = None
    encryption_key: str | None = None
    sync_interval_seconds: int = 30
    batch_size: int = 100


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BRAIN_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    data_dir: str = "./.brain"
    mode: Literal["local", "cloud_sync"] = "local"

    server: ServerSettings = Field(default_factory=ServerSettings)
    capture: CaptureSettings = Field(default_factory=CaptureSettings)
    redaction: RedactionSettings = Field(default_factory=RedactionSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    graph: GraphSettings = Field(default_factory=GraphSettings)
    cloud: CloudSettings = Field(default_factory=CloudSettings)

    @property
    def data_path(self) -> Path:
        p = Path(self.data_dir).expanduser()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def event_db_url(self) -> str:
        if self.storage.event_backend == "postgres" and self.storage.postgres_dsn:
            return self.storage.postgres_dsn
        return f"sqlite+aiosqlite:///{self.data_path / 'events.db'}"

    @property
    def graph_db_url(self) -> str:
        # The default embedded graph store shares the SQLite family; Postgres
        # reuses the same async SQLAlchemy core, so a DSN is a drop-in.
        if self.storage.graph_backend == "sqlite":
            return f"sqlite+aiosqlite:///{self.data_path / 'graph.db'}"
        if self.storage.postgres_dsn:
            return self.storage.postgres_dsn
        return f"sqlite+aiosqlite:///{self.data_path / 'graph.db'}"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_settings(config_path: str | os.PathLike[str] | None = None) -> Settings:
    """Load settings, layering an optional YAML file under env-var overrides."""
    path = config_path or os.environ.get("BRAIN_CONFIG") or "config.yaml"
    file_data: dict[str, Any] = {}
    p = Path(path)
    if p.is_file():
        with p.open("r", encoding="utf-8") as fh:
            file_data = yaml.safe_load(fh) or {}

    # Build from file first, then let BaseSettings apply env overrides on top.
    base = Settings().model_dump()
    merged = _deep_merge(base, file_data)
    return Settings(**merged)
