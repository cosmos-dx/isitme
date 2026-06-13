"""FastMCP server wiring the isitme brain tools.

The server exposes six tools, each a thin, typed call into the Web API:

* ``recall_context``   — relevant memories for a query (POST /api/recall)
* ``search_memory``    — broader semantic search (POST /api/search)
* ``get_user_profile`` — the user's learned mindset/behavior model (GET /api/profile)
* ``ask_brain``        — synthesized answer grounded in the user's brain (POST /api/ask)
* ``log_interaction``  — write an interaction/opinion back into the brain (POST /api/log)
* ``get_stats``        — brain size/health counters (GET /api/stats)
"""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from brain_mcp.client import BrainClient
from brain_mcp.config import BrainMCPConfig

SERVER_NAME = "isitme-brain"

INSTRUCTIONS = """\
This server connects you to the user's personal "central brain" — a local store \
of their captured online behavior, a knowledge graph, semantic memories, and a \
learned profile of how they think and act.

Use it to ground your responses in who this specific user is:
- Call `get_user_profile` early to understand the user's mindset, interests, and habits.
- Call `recall_context` for memories tightly relevant to the current task, or \
`search_memory` for broader exploration of what they've seen/done/written.
- Call `ask_brain` when you want a synthesized, brain-grounded answer to a question \
about the user.
- Call `log_interaction` to record a notable interaction or the user's stated opinion \
back into the brain so it improves over time.
- Call `get_stats` to gauge how much the brain currently knows.

Prefer brain-grounded facts over assumptions. If a tool reports the brain is \
unreachable or the API key is invalid, tell the user how to fix it rather than guessing.\
"""

# Allowed event types for log_interaction, mirrored from brain_core.models.events.
_EVENT_TYPES = (
    "visit",
    "click",
    "dwell",
    "link",
    "search",
    "llm_chat",
    "content_create",
    "opinion",
)


def build_server(
    config: BrainMCPConfig,
    *,
    client: BrainClient | None = None,
) -> FastMCP:
    """Construct the FastMCP server and register all brain tools.

    A single :class:`BrainClient` is shared across tool invocations. Pass
    ``client`` to inject a pre-built (e.g. mocked) client in tests.
    """
    mcp = FastMCP(
        name=SERVER_NAME,
        instructions=INSTRUCTIONS,
        host=config.host,
        port=config.port,
    )

    holder: dict[str, BrainClient | None] = {"client": client}

    def get_client() -> BrainClient:
        existing = holder["client"]
        if existing is None:
            existing = BrainClient(
                config.api_base, config.api_key, timeout=config.timeout
            )
            holder["client"] = existing
        return existing

    async def aclose() -> None:
        existing = holder["client"]
        if existing is not None:
            await existing.aclose()
            holder["client"] = None

    # Expose internals for the entrypoint lifecycle and for tests.
    mcp._brain_get_client = get_client  # type: ignore[attr-defined]
    mcp._brain_aclose = aclose  # type: ignore[attr-defined]
    mcp._brain_config = config  # type: ignore[attr-defined]

    @mcp.tool(
        title="Recall relevant context",
        description=(
            "Recall the memories most relevant to a query from the user's brain. "
            "Use this to ground your answer in what the user has actually seen, done, "
            "searched, or written. Returns the top-k matching memories with metadata."
        ),
    )
    async def recall_context(
        query: Annotated[
            str,
            Field(description="Natural-language description of the context you need."),
        ],
        k: Annotated[
            int,
            Field(default=5, ge=1, le=50, description="Max number of memories to return."),
        ] = 5,
    ) -> Any:
        return await get_client().recall(query, k)

    @mcp.tool(
        title="Search memory",
        description=(
            "Run a broader semantic search across everything the brain has captured "
            "(pages, searches, chats, notes, opinions). Prefer this for exploration; "
            "use recall_context when you want only the tightest matches for a task."
        ),
    )
    async def search_memory(
        query: Annotated[str, Field(description="What to search for across the brain.")],
        k: Annotated[
            int,
            Field(default=8, ge=1, le=50, description="Max number of results to return."),
        ] = 8,
    ) -> Any:
        return await get_client().search(query, k)

    @mcp.tool(
        title="Get user profile",
        description=(
            "Fetch the user's learned profile: their mindset, recurring interests, "
            "behavioral patterns, top domains/topics, and a summary of how they think "
            "and act online. Call this early to personalize your responses."
        ),
    )
    async def get_user_profile() -> Any:
        return await get_client().profile()

    @mcp.tool(
        title="Ask the brain",
        description=(
            "Ask a natural-language question about the user and get a synthesized "
            "answer grounded in their brain (memories + profile), along with the "
            "sources used. Best when you want a direct answer rather than raw memories."
        ),
    )
    async def ask_brain(
        question: Annotated[str, Field(description="The question to ask about the user.")],
        k: Annotated[
            int,
            Field(default=6, ge=1, le=50, description="How many sources to ground on."),
        ] = 6,
    ) -> Any:
        return await get_client().ask(question, k)

    @mcp.tool(
        title="Log interaction",
        description=(
            "Record an interaction or the user's stated opinion back into the brain so "
            "it learns over time. Use `type='opinion'` to capture a belief/preference the "
            "user expressed, or `type='llm_chat'` to log a notable LLM exchange. Provide "
            "free-text `content` and any structured extras in `data`."
        ),
    )
    async def log_interaction(
        type: Annotated[
            str,
            Field(
                description=(
                    "Event type. One of: "
                    + ", ".join(_EVENT_TYPES)
                    + ". Use 'opinion' for stated beliefs/preferences."
                )
            ),
        ],
        content: Annotated[
            str | None,
            Field(default=None, description="Free-text body (the message, note, or opinion)."),
        ] = None,
        url: Annotated[
            str | None,
            Field(default=None, description="Associated URL, if any."),
        ] = None,
        title: Annotated[
            str | None,
            Field(default=None, description="Short human-readable title, if any."),
        ] = None,
        data: Annotated[
            dict[str, Any] | None,
            Field(default=None, description="Type-specific structured extras."),
        ] = None,
    ) -> Any:
        event_type = type.strip().lower()
        if event_type not in _EVENT_TYPES:
            raise ValueError(
                f"Invalid event type {type!r}. Choose one of: {', '.join(_EVENT_TYPES)}."
            )
        event: dict[str, Any] = {"type": event_type, "source": "mcp"}
        if content is not None:
            event["content"] = content
        if url is not None:
            event["url"] = url
        if title is not None:
            event["title"] = title
        if data:
            event["data"] = data
        return await get_client().log(event)

    @mcp.tool(
        title="Get brain stats",
        description=(
            "Return counters describing how much the brain currently knows (events, "
            "graph nodes/edges, memories) and its operating mode/embedding provider. "
            "Use to gauge coverage before relying on recall/search."
        ),
    )
    async def get_stats() -> Any:
        return await get_client().stats()

    return mcp
