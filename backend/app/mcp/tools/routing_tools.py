"""MCP write tool: assign_bug — manual Bug→Epic routing (TASK-7-010)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.models.epic import Epic
from app.models.node_bug_report import NodeBugReport
from app.services import event_bus
from app.services.audit import write_audit
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, http_status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": {"code": code, "message": message, "status": http_status}}))]


def _resolve_actor(args: dict) -> tuple[uuid.UUID, str]:
    role = str(args.get("_actor_role", "admin"))
    raw = args.get("_actor_id", str(ADMIN_ID))
    try:
        actor_id = raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))
    except ValueError:
        actor_id = ADMIN_ID
    return actor_id, role


def _parse_uuid(value: object) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


register_tool(
    Tool(
        name="hivemind-assign_bug",
        description=(
            "Manually assign a node_bug_report to an epic. "
            "Use when pgvector auto-routing score is below threshold. "
            "Requires admin role. Set force=true to override an existing manual assignment."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "bug_report_id": {"type": "string", "description": "node_bug_reports UUID"},
                "epic_id": {"type": "string", "description": "epics UUID"},
                "reason": {"type": "string", "description": "Optional reason for the assignment"},
                "force": {"type": "boolean", "description": "Override existing manual assignment", "default": False},
            },
            "required": ["bug_report_id", "epic_id"],
        },
    ),
    handler=lambda args: _handle_assign_bug(args),
)


async def _handle_assign_bug(args: dict) -> list[TextContent]:
    actor_id, role = _resolve_actor(args)
    if role != "admin":
        return _err("PERMISSION_DENIED", "assign_bug requires admin role", 403)

    bug_report_id = _parse_uuid(args.get("bug_report_id"))
    if bug_report_id is None:
        return _err("ENTITY_NOT_FOUND", "Bug report not found", 404)

    epic_id = _parse_uuid(args.get("epic_id"))
    if epic_id is None:
        return _err("ENTITY_NOT_FOUND", "Epic not found", 404)

    reason: str = args.get("reason") or ""
    force: bool = bool(args.get("force", False))

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Validate bug report
                bug_result = await db.execute(
                    select(NodeBugReport).where(NodeBugReport.id == bug_report_id)
                )
                report = bug_result.scalar_one_or_none()
                if report is None:
                    return _err("ENTITY_NOT_FOUND", f"Bug report '{bug_report_id}' not found", 404)

                # Validate epic
                epic_result = await db.execute(select(Epic).where(Epic.id == epic_id))
                epic = epic_result.scalar_one_or_none()
                if epic is None:
                    return _err("ENTITY_NOT_FOUND", f"Epic '{epic_id}' not found", 404)

                # Check existing manual assignment
                if report.manually_routed and not force:
                    return _err(
                        "CONFLICT",
                        "Bug already manually assigned. Use force=true to override.",
                        409,
                    )

                now = datetime.now(UTC)
                report.epic_id = epic_id
                report.manually_routed = True
                report.manually_routed_by = actor_id
                report.manually_routed_at = now

                await db.flush()

        await write_audit(
            tool_name="assign_bug",
            actor_id=actor_id,
            actor_role=role,
            input_payload={
                "bug_report_id": str(bug_report_id),
                "epic_id": str(epic_id),
                "reason": reason,
                "force": force,
            },
        )

        event_bus.publish(
            "bug_manually_routed",
            {
                "bug_report_id": str(bug_report_id),
                "epic_id": str(epic_id),
                "actor_id": str(actor_id),
                "reason": reason,
            },
            channel="triage",
        )

        return _ok(
            {
                "data": {
                    "bug_report_id": str(bug_report_id),
                    "epic_id": str(epic_id),
                    "manually_routed_by": str(actor_id),
                    "manually_routed_at": now.isoformat(),
                    "reason": reason,
                }
            }
        )
    except Exception as exc:
        logger.exception("assign_bug failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
