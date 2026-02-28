"""MCP tools for semantic similarity search via pgvector."""
from __future__ import annotations

from mcp.types import Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.embedding_service import get_embedding_service


# ── Helpers ──────────────────────────────────────────────────────────────────

SEARCHABLE_TABLES = {"skills", "wiki_articles", "epics", "docs"}


def _json_response(data: list) -> list[dict]:
    return [{"type": "text", "text": str(data)}]


# ── Tool: semantic_search ────────────────────────────────────────────────────

register_tool(
    Tool(
        name="hivemind/semantic_search",
        description=(
            "Semantic similarity search across embedding-enabled tables. "
            "Returns top-N most similar records by cosine distance. "
            "Returns empty list if embeddings unavailable (Ollama down / circuit-breaker open)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language query to search for",
                },
                "table": {
                    "type": "string",
                    "description": "Table to search: skills, wiki_articles, epics, docs",
                    "enum": list(SEARCHABLE_TABLES),
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query", "table"],
        },
    ),
    handler=lambda args: _handle_semantic_search(args),
)


async def _handle_semantic_search(args: dict) -> list[dict]:
    query = args["query"]
    table = args["table"]
    limit = args.get("limit", 5)

    if table not in SEARCHABLE_TABLES:
        return [{"type": "text", "text": f"Invalid table: {table}"}]

    svc = get_embedding_service()
    async with AsyncSessionLocal() as db:
        results = await svc.search_similar(db, table, query, limit=limit)

    if not results:
        return [
            {
                "type": "text",
                "text": "No results — embeddings may be unavailable (Ollama down or circuit-breaker open)",
            }
        ]

    return _json_response(results)
