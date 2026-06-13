"""FastAPI app factory for the Web API / BFF (port 5050).

Responsibilities:
  * Google OAuth 2.0 login -> signed session cookie usable by the :4000 frontend.
  * API-key management (create/list/revoke; plaintext shown once, only hash stored).
  * MCP config generator for Cursor / Claude.
  * Read-only proxy over the Core Brain for the dashboard (graph, stats, profile,
    ask, extension usage).
"""

from __future__ import annotations

import logging
from collections import Counter
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlencode, urlparse

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from web_api import auth, mcp_config
from web_api.brain_client import BrainClient
from web_api.config import Settings, get_settings
from web_api.google_auth import GoogleTokenVerifier
from web_api.llm import LLMHelper
from web_api.models import (
    ApiKeyCreatedOut,
    ApiKeyOut,
    AskRequest,
    CreateKeyRequest,
    IngestRequest,
    McpConfigResponse,
    MeResponse,
    OAuthConfigResponse,
    QueryRequest,
    UserOut,
    ValidateKeyResponse,
)
from web_api.oauth import build_oauth
from web_api.security import generate_api_key
from web_api.store import build_store

logger = logging.getLogger("web.api")

# Extension/MCP clients authenticate with an Authorization: Bearer <google token>
# (X-API-Key is the legacy fallback) rather than cookies; allow the
# chrome-extension origin so the extension can call /api/ingest etc.
_EXTENSION_ORIGIN_REGEX = r"chrome-extension://.*"


def _is_allowed_ext_redirect(uri: str) -> bool:
    """Only allow the extension's Chrome identity redirect, to avoid turning the
    OAuth login into an open redirector. Chrome serves these at
    ``https://<extension-id>.chromiumapp.org/``."""
    try:
        parsed = urlparse(uri)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.endswith(".chromiumapp.org")
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = build_store(settings)
        await store.init()
        app.state.store = store
        app.state.brain = BrainClient(settings.brain_base_url)
        app.state.llm = LLMHelper(settings.openai_api_key)
        app.state.oauth = build_oauth(settings)
        # Verifies Google Bearer tokens (id_token / access_token) for MCP + the
        # extension. None when OAuth isn't configured (Bearer auth disabled).
        app.state.google_verifier = (
            GoogleTokenVerifier(settings.google.client_id) if settings.google else None
        )
        logger.info(
            "Web API ready (oauth=%s, brain=%s, openai=%s, store=%s).",
            settings.oauth_configured,
            settings.brain_base_url,
            app.state.llm.enabled,
            type(store).__name__,
        )
        try:
            yield
        finally:
            await app.state.brain.close()
            if app.state.google_verifier is not None:
                await app.state.google_verifier.aclose()
            await store.close()

    app = FastAPI(
        title="isitme — Web API",
        version="0.1.0",
        description="Local web BFF: Google OAuth, API keys, MCP config, brain proxy.",
        lifespan=lifespan,
    )

    # Session cookie (signed). SameSite=Lax + same-site localhost lets the
    # :4000 frontend send it on credentialed fetches and OAuth redirects.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie=settings.session_cookie,
        same_site="lax",
        https_only=False,
        max_age=60 * 60 * 24 * 14,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_origin_regex=_EXTENSION_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-API-Key", "Content-Type", "Authorization"],
    )

    # --- dependencies -------------------------------------------------------
    def get_brain(request: Request) -> BrainClient:
        return request.app.state.brain

    def get_llm(request: Request) -> LLMHelper:
        return request.app.state.llm

    # Session-only guard (browser) and combined session/Bearer/API-key guards.
    require_user = auth.require_user
    require_auth = auth.require_auth

    async def proxy_brain(coro):
        try:
            return await coro
        except Exception as exc:  # httpx errors / brain offline
            logger.warning("Brain proxy error: %s", exc)
            raise HTTPException(status_code=502, detail="Core Brain unavailable") from exc

    # --- health -------------------------------------------------------------
    @app.get("/healthz")
    async def healthz(brain: BrainClient = Depends(get_brain)) -> dict:
        return {
            "status": "ok",
            "oauth_configured": settings.oauth_configured,
            "brain_reachable": await brain.healthz(),
        }

    # --- auth ---------------------------------------------------------------
    @app.get("/auth/google/login")
    async def google_login(
        request: Request,
        ext_redirect: str | None = Query(default=None),
        ext_state: str | None = Query(default=None),
    ):
        oauth = request.app.state.oauth
        if not settings.oauth_configured or oauth is None:
            raise HTTPException(status_code=503, detail="Google OAuth is not configured")
        # Browser-extension flow: the extension can't register its own
        # chrome-extension redirect with Google, so it brokers sign-in through
        # this endpoint. We stash the (validated) chromiumapp.org redirect and
        # the callback hands the verified id_token back to it instead of opening
        # a dashboard session. Only https://*.chromiumapp.org is allowed, to
        # prevent this becoming an open redirector.
        if ext_redirect:
            if not _is_allowed_ext_redirect(ext_redirect):
                raise HTTPException(status_code=400, detail="Invalid ext_redirect")
            request.session["ext_redirect"] = ext_redirect
            request.session["ext_state"] = ext_state or ""
        else:
            request.session.pop("ext_redirect", None)
            request.session.pop("ext_state", None)
        # Honor the redirect_uri pinned in OAUTH_CLIENT_JSON exactly.
        return await oauth.google.authorize_redirect(request, settings.google.redirect_uri)

    @app.get("/auth/google/callback")
    async def google_callback(request: Request):
        oauth = request.app.state.oauth
        if not settings.oauth_configured or oauth is None:
            raise HTTPException(status_code=503, detail="Google OAuth is not configured")
        ext_redirect = request.session.pop("ext_redirect", None)
        ext_state = request.session.pop("ext_state", "")
        try:
            token = await oauth.google.authorize_access_token(request)
        except Exception as exc:
            logger.warning("OAuth callback failed: %s", exc)
            if ext_redirect:
                return RedirectResponse(f"{ext_redirect}#error=oauth_failed")
            return RedirectResponse(f"{settings.frontend_origin}/?auth_error=1")
        userinfo = token.get("userinfo") or {}
        sub = userinfo.get("sub")
        if not sub:
            if ext_redirect:
                return RedirectResponse(f"{ext_redirect}#error=no_sub")
            return RedirectResponse(f"{settings.frontend_origin}/?auth_error=1")
        user_id = await request.app.state.store.upsert_user(
            google_sub=sub,
            email=userinfo.get("email"),
            name=userinfo.get("name"),
            picture=userinfo.get("picture"),
        )
        # Extension flow: return the verified Google id_token to the extension's
        # chromiumapp.org redirect (in the URL fragment). The extension sends it
        # back as `Authorization: Bearer` and the GoogleTokenVerifier re-verifies
        # it. No browser session is created here.
        if ext_redirect:
            id_token = token.get("id_token")
            if not id_token:
                return RedirectResponse(f"{ext_redirect}#error=no_id_token")
            fragment = urlencode(
                {
                    "id_token": id_token,
                    "state": ext_state,
                    "expires_in": str(token.get("expires_in", 3600)),
                }
            )
            return RedirectResponse(f"{ext_redirect}#{fragment}")
        request.session["user_id"] = user_id
        return RedirectResponse(settings.dashboard_url)

    @app.get("/auth/oauth-config", response_model=OAuthConfigResponse)
    async def oauth_config() -> OAuthConfigResponse:
        """Public, non-secret OAuth client info so local clients (MCP CLI,
        extension) can initiate Google sign-in without hardcoding the client_id.

        Never returns the client_secret. ``loopback_redirect_uris`` lists any
        registered ``http://127.0.0.1``/``localhost`` redirect URIs usable by a
        CLI loopback flow.
        """
        google = settings.google
        if google is None:
            return OAuthConfigResponse(configured=False)
        loopback = [
            uri
            for uri in google.redirect_uris
            if uri.startswith("http://127.0.0.1") or uri.startswith("http://localhost")
        ]
        return OAuthConfigResponse(
            configured=True,
            client_id=google.client_id,
            auth_uri=google.auth_uri,
            token_uri=google.token_uri,
            scopes=["openid", "email", "profile"],
            redirect_uris=google.redirect_uris,
            loopback_redirect_uris=loopback,
        )

    @app.get("/auth/me", response_model=MeResponse)
    async def auth_me(request: Request) -> MeResponse:
        # Resolves a session cookie OR a Google Bearer token OR a legacy API key,
        # so MCP / extension clients can confirm who their token authenticates as.
        user = await auth.authenticate(request)
        if not user:
            return MeResponse(authenticated=False)
        return MeResponse(
            authenticated=True,
            user=UserOut(
                id=user["id"],
                email=user.get("email"),
                name=user.get("name"),
                picture=user.get("picture"),
            ),
        )

    @app.post("/auth/logout")
    async def logout(request: Request) -> dict:
        request.session.clear()
        return {"ok": True}

    # --- API keys -----------------------------------------------------------
    @app.post("/api/keys", response_model=ApiKeyCreatedOut)
    async def create_key(
        body: CreateKeyRequest,
        request: Request,
        user: dict[str, Any] = Depends(require_user),
    ) -> ApiKeyCreatedOut:
        generated = generate_api_key()
        meta = await request.app.state.store.create_api_key(
            user["id"], body.name, generated
        )
        return ApiKeyCreatedOut(**meta, key=generated.plaintext)

    @app.get("/api/keys", response_model=list[ApiKeyOut])
    async def list_keys(
        request: Request, user: dict[str, Any] = Depends(require_user)
    ) -> list[ApiKeyOut]:
        rows = await request.app.state.store.list_api_keys(user["id"])
        return [ApiKeyOut(**row) for row in rows]

    @app.delete("/api/keys/{key_id}")
    async def delete_key(
        key_id: str, request: Request, user: dict[str, Any] = Depends(require_user)
    ) -> dict:
        ok = await request.app.state.store.revoke_api_key(user["id"], key_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Key not found")
        return {"ok": True, "id": key_id, "revoked": True}

    @app.get("/api/keys/validate", response_model=ValidateKeyResponse)
    async def validate_key(
        user: dict[str, Any] = Depends(auth.require_api_key),
    ) -> ValidateKeyResponse:
        """Verify a presented ``X-API-Key`` and echo the owning user."""
        return ValidateKeyResponse(
            valid=True,
            user=UserOut(
                id=user["id"],
                email=user.get("email"),
                name=user.get("name"),
                picture=user.get("picture"),
            ),
        )

    # --- MCP config ---------------------------------------------------------
    @app.get("/api/mcp-config", response_model=McpConfigResponse)
    async def mcp_config_endpoint(
        request: Request,
        user: dict[str, Any] = Depends(require_user),
        mint: bool = Query(default=False, description="Mint a new key and embed it once"),
        name: str = Query(default="mcp"),
        key: str | None = Query(default=None, description="Existing plaintext key to embed"),
    ) -> McpConfigResponse:
        embedded_key: str | None = None
        prefix: str | None = None
        using_existing = False
        if mint:
            generated = generate_api_key()
            meta = await request.app.state.store.create_api_key(user["id"], name, generated)
            embedded_key = generated.plaintext
            prefix = meta["prefix"]
        elif key:
            embedded_key = key
            prefix = key[:12]
            using_existing = True
        cfg = mcp_config.build_mcp_config(settings.brain_public_url, embedded_key)
        return McpConfigResponse(
            brain_url=settings.brain_public_url,
            api_key_prefix=prefix,
            using_existing_key=using_existing,
            config=cfg,
            snippet=mcp_config.build_snippet(cfg),
            instructions=mcp_config.build_instructions(settings.brain_public_url),
        )

    # --- brain proxy (session OR X-API-Key) ---------------------------------
    @app.post("/api/ingest")
    async def api_ingest(
        body: IngestRequest,
        request: Request,
        brain: BrainClient = Depends(get_brain),
        user: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        result = await proxy_brain(brain.ingest(body.model_dump()))
        await request.app.state.store.record_usage(user["id"], "ingest")
        return result

    @app.post("/api/log")
    async def api_log(
        event: dict[str, Any],
        request: Request,
        brain: BrainClient = Depends(get_brain),
        user: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        result = await proxy_brain(brain.log_one(event))
        await request.app.state.store.record_usage(user["id"], "log")
        return result

    @app.post("/api/recall")
    async def api_recall(
        body: QueryRequest,
        brain: BrainClient = Depends(get_brain),
        _: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        return await proxy_brain(brain.recall(body.query, body.k))

    @app.post("/api/search")
    async def api_search(
        body: QueryRequest,
        brain: BrainClient = Depends(get_brain),
        _: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        return await proxy_brain(brain.search_memory(body.query, body.k))

    @app.get("/api/graph")
    async def api_graph(
        node_limit: int = Query(default=1500, ge=1, le=5000),
        edge_limit: int = Query(default=4000, ge=1, le=20000),
        brain: BrainClient = Depends(get_brain),
        _: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        raw = await proxy_brain(brain.graph(node_limit, edge_limit))
        return _shape_force_graph(raw)

    @app.get("/api/stats")
    async def api_stats(
        brain: BrainClient = Depends(get_brain),
        _: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        return await proxy_brain(brain.stats())

    @app.get("/api/profile")
    async def api_profile(
        brain: BrainClient = Depends(get_brain),
        _: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        return await proxy_brain(brain.profile())

    @app.post("/api/ask")
    async def api_ask(
        body: AskRequest,
        brain: BrainClient = Depends(get_brain),
        llm: LLMHelper = Depends(get_llm),
        _: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        result = await proxy_brain(brain.ask(body.question, body.k))
        synthesized = await llm.synthesize_answer(
            body.question,
            result.get("sources", []),
            result.get("profile_summary", ""),
        )
        if synthesized:
            result["answer"] = synthesized
            result["synthesized_by"] = "openai"
        return result

    @app.get("/api/extension/usage")
    async def api_extension_usage(
        brain: BrainClient = Depends(get_brain),
        _: dict[str, Any] = Depends(require_auth),
    ) -> dict:
        stats = await proxy_brain(brain.stats())
        # Brain has no per-event-category counter; approximate a breakdown from
        # the knowledge-graph node types, which mirror what the extension feeds.
        by_category: dict[str, int] = {}
        try:
            graph = await brain.graph(node_limit=2000, edge_limit=1)
            by_category = dict(Counter(n.get("type", "unknown") for n in graph.get("nodes", [])))
        except Exception:  # best-effort enrichment
            by_category = {}
        return {
            "events_captured": stats.get("events", 0),
            "nodes": stats.get("nodes", 0),
            "edges": stats.get("edges", 0),
            "memories": stats.get("memories", 0),
            "mode": stats.get("mode"),
            "embedding_provider": stats.get("embedding_provider"),
            "by_category": by_category,
            # Not tracked by the brain yet; surfaced as null so the UI can label it.
            "last_sync": None,
            "active_days": None,
        }

    return app


_TYPE_COLORS = {
    "user": "#f5f5f5",
    "domain": "#7c5cff",
    "url": "#4f8cff",
    "topic": "#22d3ee",
    "query": "#34d399",
    "llm": "#f59e0b",
    "opinion": "#f472b6",
    "document": "#a78bfa",
    "person": "#fb7185",
}


def _shape_force_graph(raw: dict[str, Any]) -> dict[str, Any]:
    """Reshape brain nodes/edges into react-force-graph ``{nodes, links}``."""
    nodes = []
    for n in raw.get("nodes", []):
        weight = float(n.get("weight", 0.0) or 0.0)
        node_type = n.get("type", "unknown")
        nodes.append(
            {
                "id": n["id"],
                "label": n.get("label", ""),
                "type": node_type,
                "weight": round(weight, 3),
                "val": max(1.0, weight),
                "color": _TYPE_COLORS.get(node_type, "#9ca3af"),
                "attributes": n.get("attributes", {}),
            }
        )
    links = []
    for e in raw.get("edges", []):
        eff = e.get("effective_weight")
        links.append(
            {
                "source": e["src"],
                "target": e["dst"],
                "relation": e.get("relation", ""),
                "weight": round(float(eff if eff is not None else e.get("weight", 0.0)), 3),
            }
        )
    return {"nodes": nodes, "links": links}
