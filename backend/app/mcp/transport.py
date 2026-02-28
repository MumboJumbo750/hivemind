"""MCP HTTP/SSE Transport — FastAPI routes (TASK-3-001).

Provides ``/api/mcp/sse`` for Server-Sent Events transport and
``/api/mcp/call`` for direct HTTP tool invocations.
AuthN via JWT (reuses Phase 2 auth middleware).
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from app.mcp.server import _tool_definitions, _tool_handlers, call_tool
import app.mcp.tools  # noqa: F401 — ensure all tools are registered
from app.routers.deps import CurrentActor, get_current_actor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ── Request / Response Models ──────────────────────────────────────────────

class McpCallRequest(BaseModel):
    """HTTP envelope for a single MCP tool call."""
    tool: str
    arguments: dict | None = None


class McpCallResponse(BaseModel):
    """HTTP response for a single MCP tool call."""
    result: list[dict]


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/tools")
async def list_mcp_tools(actor: CurrentActor = Depends(get_current_actor)):
    """List all available MCP tools (HTTP transport)."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.inputSchema,
        }
        for t in _tool_definitions
    ]


@router.post("/call", response_model=McpCallResponse)
async def call_mcp_tool(
    body: McpCallRequest,
    actor: CurrentActor = Depends(get_current_actor),
):
    """Execute a single MCP tool call via HTTP."""
    if body.tool not in _tool_handlers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{body.tool}' not found",
        )

    # Inject actor context for audit
    args = dict(body.arguments or {})
    args["_actor_id"] = str(actor.id)
    args["_actor_role"] = actor.role

    result = await call_tool(body.tool, args)
    return McpCallResponse(result=[{"type": r.type, "text": r.text} for r in result])


@router.get("/sse")
async def mcp_sse(actor: CurrentActor = Depends(get_current_actor)):
    """SSE transport for MCP — streams tool-call results as Server-Sent Events.

    This endpoint provides a persistent SSE connection for MCP clients that
    prefer the streaming transport. The client sends tool calls via ``POST /api/mcp/call``
    and receives broadcast results here.
    """
    from app.services.event_bus import subscribe, unsubscribe

    async def event_generator():
        q = subscribe()
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    event_type = msg.get("event", "message")
                    data = json.dumps(msg.get("data", {}))
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ":keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unsubscribe(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
