"""MCP write tools for dead-letter queue management (TASK-7-008)."""

from __future__ import annotations

import json
import logging
import uuid

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.dlq_service import DlqError, discard_dead_letter, requeue_dead_letter
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ALLOWED_ROLES = {"admin", "triage"}


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": {"code": code, "message": message, "status": status}}))]


def _resolve_actor(args: dict) -> tuple[uuid.UUID, str]:
    role = str(args.get("_actor_role", "admin"))
    actor_raw = args.get("_actor_id", str(ADMIN_ID))
    try:
        actor_id = actor_raw if isinstance(actor_raw, uuid.UUID) else uuid.UUID(str(actor_raw))
    except ValueError:
        actor_id = ADMIN_ID
    return actor_id, role


def _require_dlq_permission(args: dict) -> list[TextContent] | None:
    _actor_id, role = _resolve_actor(args)
    if role not in ALLOWED_ROLES:
        return _err(
            "PERMISSION_DENIED",
            f"Role '{role}' is not allowed. Required: admin or triage",
            403,
        )
    return None


def _parse_dead_letter_id(args: dict) -> tuple[uuid.UUID | None, list[TextContent] | None]:
    try:
        return uuid.UUID(args["id"]), None
    except (KeyError, ValueError):
        return None, _err("VALIDATION_ERROR", "Invalid or missing dead-letter id", 422)


register_tool(
    Tool(
        name="hivemind-requeue_dead_letter",
        description=(
            "Requeue a sync_dead_letter entry by creating a new sync_outbox entry with "
            "state='pending', attempts=0, next_retry_at=NULL."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "sync_dead_letter UUID"},
            },
            "required": ["id"],
        },
    ),
    handler=lambda args: _handle_requeue_dead_letter(args),
)


async def _handle_requeue_dead_letter(args: dict) -> list[TextContent]:
    denied = _require_dlq_permission(args)
    if denied:
        return denied

    dead_letter_id, parse_error = _parse_dead_letter_id(args)
    if parse_error:
        return parse_error

    actor_id, _role = _resolve_actor(args)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await requeue_dead_letter(db, dead_letter_id, actor_id)
        return _ok({"data": result})
    except DlqError as exc:
        return _err(exc.code, str(exc), exc.status)
    except Exception as exc:
        logger.exception("requeue_dead_letter failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


register_tool(
    Tool(
        name="hivemind-discard_dead_letter",
        description=(
            "Discard a sync_dead_letter entry (soft action): sets discarded_at/by, "
            "keeps row for audit trail."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "sync_dead_letter UUID"},
            },
            "required": ["id"],
        },
    ),
    handler=lambda args: _handle_discard_dead_letter(args),
)


async def _handle_discard_dead_letter(args: dict) -> list[TextContent]:
    denied = _require_dlq_permission(args)
    if denied:
        return denied

    dead_letter_id, parse_error = _parse_dead_letter_id(args)
    if parse_error:
        return parse_error

    actor_id, _role = _resolve_actor(args)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await discard_dead_letter(db, dead_letter_id, actor_id)
        return _ok({"data": result})
    except DlqError as exc:
        return _err(exc.code, str(exc), exc.status)
    except Exception as exc:
        logger.exception("discard_dead_letter failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
