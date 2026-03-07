"""MCP Write-Tools for Triage — route and ignore events.

RBAC: admin-only with triage permission.
"""
from __future__ import annotations

import uuid

from mcp.types import Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.triage_service import (
    TriageConflictError,
    TriageNotFoundError,
    ignore_event,
    route_event,
)

# Solo-mode admin
ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


# ── Tool: route_event ────────────────────────────────────────────────────────

register_tool(
    Tool(
        name="hivemind-route_event",
        description=(
            "Route an unrouted sync_outbox event to a specific epic. "
            "Sets routing_state='routed', writes audit log, broadcasts SSE event. "
            "Returns 409 if event is not in 'unrouted' state."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "UUID of the sync_outbox event to route",
                },
                "epic_id": {
                    "type": "string",
                    "description": "Epic key or UUID to route the event to",
                },
            },
            "required": ["event_id", "epic_id"],
        },
    ),
    handler=lambda args: _handle_route_event(args),
)


async def _handle_route_event(args: dict) -> list[dict]:
    event_id = args["event_id"]
    epic_id = args["epic_id"]

    try:
        async with AsyncSessionLocal() as db:
            result = await route_event(db, event_id, epic_id, ADMIN_ID)
        return [{"type": "text", "text": str(result)}]
    except TriageNotFoundError:
        return [{"type": "text", "text": f"Event {event_id} not found"}]
    except TriageConflictError as exc:
        return [
            {
                "type": "text",
                "text": f"409 Conflict: {exc}",
            }
        ]


# ── Tool: ignore_event ──────────────────────────────────────────────────────

register_tool(
    Tool(
        name="hivemind-ignore_event",
        description=(
            "Ignore an unrouted sync_outbox event with optional reason. "
            "Sets routing_state='ignored', writes audit log, broadcasts SSE event. "
            "Returns 409 if event is not in 'unrouted' state."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "UUID of the sync_outbox event to ignore",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason for ignoring the event",
                    "default": "",
                },
            },
            "required": ["event_id"],
        },
    ),
    handler=lambda args: _handle_ignore_event(args),
)


async def _handle_ignore_event(args: dict) -> list[dict]:
    event_id = args["event_id"]
    reason = args.get("reason", "")

    try:
        async with AsyncSessionLocal() as db:
            result = await ignore_event(db, event_id, ADMIN_ID, reason=reason)
        return [{"type": "text", "text": str(result)}]
    except TriageNotFoundError:
        return [{"type": "text", "text": f"Event {event_id} not found"}]
    except TriageConflictError as exc:
        return [
            {
                "type": "text",
                "text": f"409 Conflict: {exc}",
            }
        ]
