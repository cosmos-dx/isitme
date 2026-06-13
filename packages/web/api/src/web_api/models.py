"""Pydantic request/response schemas for the Web API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None


class MeResponse(BaseModel):
    authenticated: bool
    user: UserOut | None = None


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: str
    last_used: str | None = None
    revoked: bool = False


class ApiKeyCreatedOut(ApiKeyOut):
    # Returned exactly once, on creation.
    key: str


class CreateKeyRequest(BaseModel):
    name: str = Field(default="default", min_length=1, max_length=80)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default=6, ge=1, le=50)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    k: int = Field(default=5, ge=1, le=50)


class IngestRequest(BaseModel):
    client: str = "unknown"
    client_version: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)


class ValidateKeyResponse(BaseModel):
    valid: bool
    user: UserOut | None = None


class McpConfigResponse(BaseModel):
    brain_url: str
    api_key_prefix: str | None = None
    using_existing_key: bool
    config: dict[str, Any]
    snippet: str
    instructions: str
