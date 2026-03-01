"""MCP Standard-Compliant HTTP/SSE Transport (MCP 1.0).

Provides the official MCP SSE transport endpoints:
  - ``GET  /api/mcp/sse``       — SSE stream (JSON-RPC 2.0 responses)
  - ``POST /api/mcp/message``   — JSON-RPC 2.0 requests (initialize, tools/list, tools/call)

Plus convenience endpoints for the Hivemind frontend:
  - ``GET  /api/mcp/tools``     — flat JSON tools list
  - ``POST /api/mcp/call``      — simple tool call (no JSON-RPC overhead)

External MCP clients (Cursor, Claude Desktop HTTP, Continue) connect via /sse + /message.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from mcp.server.sse import SseServerTransport

from app.mcp.server import server, _tool_definitions, _tool_handlers, call_tool
import app.mcp.tools  # noqa: F401 — ensure all tools are registered
from app.routers.deps import CurrentActor, get_current_actor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

# ── Standard MCP SSE Transport ─────────────────────────────────────────────

_sse_transport = SseServerTransport("/api/mcp/message")

# Track active sessions for status
_active_sessions: list[asyncio.Task] = []


class _SseApp:
    """Raw ASGI app for the MCP SSE endpoint.

    Uses a class so Starlette ``Route`` treats it as a raw ASGI app
    (bypasses ``request_response`` wrapper which would choke on None return).
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async with _sse_transport.connect_sse(scope, receive, send) as streams:
            read_stream, write_stream = streams
            init_options = server.create_initialization_options()
            task = asyncio.current_task()
            if task:
                _active_sessions.append(task)
            try:
                await server.run(read_stream, write_stream, init_options)
            except asyncio.CancelledError:
                pass
            finally:
                if task and task in _active_sessions:
                    _active_sessions.remove(task)


class _MessageApp:
    """Raw ASGI app for the MCP JSON-RPC message endpoint.

    ``handle_post_message`` sends the 202 response internally via ASGI,
    so this must NOT be wrapped in ``request_response``.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await _sse_transport.handle_post_message(scope, receive, send)


# These are added as raw Starlette routes (not FastAPI) because the SDK
# needs raw ASGI scope/receive/send access for SSE streaming.
# Using class instances as endpoints prevents the request_response wrapper.
mcp_standard_routes = [
    Route("/api/mcp/sse", endpoint=_SseApp()),
    Route("/api/mcp/message", endpoint=_MessageApp(), methods=["POST"]),
]


# ── Convenience Endpoints (Hivemind Frontend) ──────────────────────────────

class McpCallRequest(BaseModel):
    """HTTP envelope for a single MCP tool call."""
    tool: str
    arguments: dict | None = None


class McpCallResponse(BaseModel):
    """HTTP response for a single MCP tool call."""
    result: list[dict]


@router.get("/tools")
async def list_mcp_tools(actor: CurrentActor = Depends(get_current_actor)):
    """List all available MCP tools (convenience endpoint for frontend)."""
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
    """Execute a single MCP tool call (convenience endpoint for frontend).

    Wraps the internal call_tool function — no JSON-RPC overhead.
    """
    if body.tool not in _tool_handlers:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{body.tool}' not found",
        )

    args = dict(body.arguments or {})
    args["_actor_id"] = str(actor.id)
    args["_actor_role"] = actor.role

    result = await call_tool(body.tool, args)
    return McpCallResponse(result=[{"type": r.type, "text": r.text} for r in result])


# ── Status Endpoint ────────────────────────────────────────────────────────

@router.get("/status")
async def mcp_status(actor: CurrentActor = Depends(get_current_actor)):
    """Return MCP server status and capabilities."""
    return {
        "protocol": "MCP 1.0",
        "transport": "sse",
        "tools_count": len(_tool_definitions),
        "connected_sessions": len(_active_sessions),
        "endpoints": {
            "sse": "/api/mcp/sse",
            "message": "/api/mcp/message",
            "tools": "/api/mcp/tools",
            "call": "/api/mcp/call",
        },
    }

