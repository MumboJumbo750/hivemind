"""Hivemind MCP Server — MCP 1.0 Standard (TASK-3-001).

Provides Model Context Protocol tools under the ``hivemind/`` namespace.

Transports (always available via FastAPI):
  - **SSE** (standard): ``GET /api/mcp/sse`` + ``POST /api/mcp/message``
    JSON-RPC 2.0 over SSE — for external MCP clients (Cursor, Claude Desktop, Continue)
  - **Convenience REST**: ``GET /api/mcp/tools`` + ``POST /api/mcp/call``
    Simple JSON — for the Hivemind frontend
  - **stdio**: for local AI clients when started with ``HIVEMIND_TRANSPORT=stdio``

Tool registration via :func:`register_tool` in ``app/mcp/tools/``.
Auth: SSE/REST uses JWT/solo-token from Phase 2, stdio uses local API-Key.
Every tool call is audited to ``mcp_invocations``.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from app.config import settings
from app.db import AsyncSessionLocal
from app.services.audit import write_audit

logger = logging.getLogger(__name__)

# ── Singleton MCP-Server instance ──────────────────────────────────────────

server = Server("hivemind")

# ── Tool Registry ──────────────────────────────────────────────────────────
# Tool definitions are accumulated here by register functions in tools/*
_tool_definitions: list[Tool] = []
_tool_handlers: dict[str, Any] = {}


def register_tool(tool: Tool, handler: Any) -> None:
    """Register an MCP tool definition and its async handler."""
    _tool_definitions.append(tool)
    _tool_handlers[tool.name] = handler
    logger.info("MCP Tool registered: %s", tool.name)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return all registered MCP tools."""
    return list(_tool_definitions)


@server.call_tool()
async def call_tool(name: str, arguments: dict | None = None) -> list[TextContent]:
    """Dispatch a tool call to the registered handler with audit logging."""
    handler = _tool_handlers.get(name)
    if handler is None:
        return [TextContent(
            type="text",
            text=json.dumps({"error": {"code": "tool_not_found", "message": f"Unknown tool: {name}"}})
        )]

    args = arguments or {}
    t0 = time.perf_counter()
    actor_id = args.pop("_actor_id", None) or uuid.UUID("00000000-0000-0000-0000-000000000001")
    actor_role = args.pop("_actor_role", "admin")

    try:
        result = await handler(args)
        duration_ms = int((time.perf_counter() - t0) * 1000)

        # Non-blocking audit
        await write_audit(
            tool_name=name,
            actor_id=actor_id if isinstance(actor_id, uuid.UUID) else uuid.UUID(str(actor_id)),
            actor_role=actor_role,
            input_payload=args,
            output_payload={"preview": result[0].text[:500] if result else ""},
            duration_ms=duration_ms,
        )
        return result

    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        logger.exception("MCP tool call failed: %s", name)

        await write_audit(
            tool_name=name,
            actor_id=actor_id if isinstance(actor_id, uuid.UUID) else uuid.UUID(str(actor_id)),
            actor_role=actor_role,
            input_payload=args,
            output_payload={"error": str(exc)},
            duration_ms=duration_ms,
        )

        error_response = {"error": {"code": "internal_error", "message": str(exc)}}
        return [TextContent(type="text", text=json.dumps(error_response))]
