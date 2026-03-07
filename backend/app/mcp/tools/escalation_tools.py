"""MCP Escalation & Decision Write Tools — Phase 6.

- hivemind-resolve_decision_request — Resolve an open decision request (TASK-6-005)
- hivemind-resolve_escalation — Resolve escalated task → in_progress (TASK-6-006)
- hivemind-reassign_epic_owner — Change epic owner/backup_owner (TASK-6-007)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from mcp.types import TextContent, Tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.audit import write_audit

logger = logging.getLogger(__name__)

# Default solo-mode admin; tools accept optional actor_id to track actual caller
ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _resolve_actor(args: dict) -> uuid.UUID:
    """Return actor_id from args or fall back to solo ADMIN_ID."""
    raw = args.get("actor_id")
    if raw:
        try:
            return uuid.UUID(str(raw))
        except ValueError:
            pass
    return ADMIN_ID


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-resolve_decision_request — TASK-6-005
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-resolve_decision_request",
        description=(
            "Resolve an open decision request. Sets state=resolved, creates "
            "DecisionRecord, and atomically transitions associated task "
            "blocked → in_progress. Owner or Admin can resolve.\n"
            "Params: decision_request_id (NOT id!), decision (NOT chosen_option!), "
            "rationale (NOT comment!). All param names are exact — use them as listed."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "decision_request_id": {
                    "type": "string",
                    "description": "UUID of the decision request to resolve",
                },
                "decision": {
                    "type": "string",
                    "description": "The chosen option / decision text",
                },
                "rationale": {
                    "type": "string",
                    "description": "Rationale for the decision",
                },
            },
            "required": ["decision_request_id", "decision"],
        },
    ),
    handler=lambda args: _handle_resolve_decision_request(args),
)


async def _handle_resolve_decision_request(args: dict) -> list[TextContent]:
    from app.models.decision import DecisionRecord, DecisionRequest
    from app.models.task import Task

    # --- Alias normalization ---
    for wrong, right in [("id", "decision_request_id"), ("chosen_option", "decision"), ("comment", "rationale")]:
        if wrong in args and right not in args:
            args[right] = args.pop(wrong)

    dr_id_str = args.get("decision_request_id", "")
    decision = args.get("decision", "").strip()
    rationale = args.get("rationale", "").strip()

    if not decision:
        return _err("VALIDATION_ERROR", "'decision' must not be empty (use param name 'decision', NOT 'chosen_option')", 422)

    try:
        dr_id = uuid.UUID(dr_id_str)
    except (ValueError, AttributeError):
        return _err("VALIDATION_ERROR", f"Invalid decision_request_id: '{dr_id_str}' — use param name 'decision_request_id' (NOT 'id')", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Load DR
                result = await db.execute(
                    select(DecisionRequest).where(DecisionRequest.id == dr_id)
                )
                dr = result.scalar_one_or_none()
                if not dr:
                    return _err("ENTITY_NOT_FOUND", f"DecisionRequest {dr_id} not found", 404)

                if dr.state != "open":
                    return _err(
                        "CONFLICT",
                        f"DecisionRequest state is '{dr.state}', expected 'open'",
                        409,
                    )

                now = datetime.now(timezone.utc)

                actor = _resolve_actor(args)

                # Resolve DR
                dr.state = "resolved"
                dr.resolved_by = actor
                dr.resolved_at = now
                dr.version += 1
                await db.flush()

                # Create DecisionRecord
                record = DecisionRecord(
                    epic_id=dr.epic_id,
                    decision_request_id=dr.id,
                    decision=decision,
                    rationale=rationale or None,
                    decided_by=actor,
                )
                db.add(record)
                await db.flush()

                # Atomically transition task blocked → in_progress
                task_info = None
                if dr.task_id:
                    task_result = await db.execute(
                        select(Task).where(Task.id == dr.task_id)
                    )
                    task = task_result.scalar_one_or_none()
                    if task and task.state == "blocked":
                        task.state = "in_progress"
                        task.version += 1
                        await db.flush()
                        task_info = {
                            "task_key": task.task_key,
                            "previous_state": "blocked",
                            "new_state": "in_progress",
                        }

                # Audit
                await write_audit(
                    tool_name="resolve_decision_request",
                    actor_id=actor,
                    actor_role="admin",
                    input_payload={
                        "decision_request_id": str(dr_id),
                        "decision": decision,
                        "rationale": rationale,
                    },
                    target_id=str(dr_id),
                )

                return _ok({
                    "data": {
                        "decision_request_id": str(dr.id),
                        "state": "resolved",
                        "decision_record_id": str(record.id),
                        "task_transition": task_info,
                    },
                    "meta": {"version": dr.version},
                })

    except Exception as exc:
        logger.exception("resolve_decision_request failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-resolve_escalation — TASK-6-006
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-resolve_escalation",
        description=(
            "Resolve an escalated task: escalated → in_progress. "
            "Admin only. Resets qa_failed_count to 0. "
            "Works for both escalation sources (3x qa_failed, decision SLA).\n"
            "Param: task_key (NOT task_id!)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {
                    "type": "string",
                    "description": "The escalated task's key",
                },
                "comment": {
                    "type": "string",
                    "description": "Admin resolution comment",
                },
            },
            "required": ["task_key"],
        },
    ),
    handler=lambda args: _handle_resolve_escalation(args),
)


async def _handle_resolve_escalation(args: dict) -> list[TextContent]:
    from app.models.task import Task
    from app.services.notification_service import create_notification

    # --- Alias normalization ---
    if "task_id" in args and "task_key" not in args:
        args["task_key"] = args.pop("task_id")

    task_key = args.get("task_key", "")
    comment = args.get("comment", "").strip()
    actor = _resolve_actor(args)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' not found", 404)

                if task.state != "escalated":
                    return _err(
                        "CONFLICT",
                        f"Task state is '{task.state}', expected 'escalated'",
                        409,
                    )

                previous_state = task.state
                task.state = "in_progress"
                task.qa_failed_count = 0
                if comment:
                    task.review_comment = comment
                task.version += 1
                await db.flush()

                # Notify assigned worker
                if task.assigned_to:
                    await create_notification(
                        db,
                        user_id=task.assigned_to,
                        notification_type="task_assigned",
                        title="Eskalation aufgelöst",
                        body=f"Task '{task.title}' ({task.task_key}) wurde von Admin de-eskaliert. Du kannst weiterarbeiten.",
                        link=f"/tasks/{task.task_key}",
                        entity_type="task",
                        entity_id=str(task.id),
                    )

                # Audit
                await write_audit(
                    tool_name="resolve_escalation",
                    actor_id=actor,
                    actor_role="admin",
                    input_payload={"task_key": task_key, "comment": comment},
                    target_id=str(task.id),
                )

                return _ok({
                    "data": {
                        "task_key": task.task_key,
                        "previous_state": previous_state,
                        "new_state": task.state,
                        "qa_failed_count": task.qa_failed_count,
                    },
                    "meta": {"version": task.version},
                })

    except Exception as exc:
        logger.exception("resolve_escalation failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-reassign_epic_owner — TASK-6-007
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-reassign_epic_owner",
        description=(
            "Admin tool: change epic owner_id and/or backup_owner_id. "
            "Validates that target users exist.\n"
            "Param: epic_key (NOT epic_id!), owner_id, backup_owner_id."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "epic_key": {"type": "string", "description": "Epic key to update"},
                "owner_id": {
                    "type": "string",
                    "description": "New owner UUID (optional)",
                },
                "backup_owner_id": {
                    "type": "string",
                    "description": "New backup owner UUID (optional, 'null' to clear)",
                },
            },
            "required": ["epic_key"],
        },
    ),
    handler=lambda args: _handle_reassign_epic_owner(args),
)


async def _handle_reassign_epic_owner(args: dict) -> list[TextContent]:
    from app.models.epic import Epic
    from app.models.user import User
    from app.services.notification_service import create_notification

    # --- Alias normalization ---
    if "epic_id" in args and "epic_key" not in args:
        args["epic_key"] = args.pop("epic_id")
    if "new_owner_id" in args and "owner_id" not in args:
        args["owner_id"] = args.pop("new_owner_id")

    epic_key = args.get("epic_key", "")
    new_owner = args.get("owner_id")
    new_backup = args.get("backup_owner_id")
    actor = _resolve_actor(args)

    if not new_owner and not new_backup:
        return _err("VALIDATION_ERROR", "Provide at least owner_id or backup_owner_id", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(Epic).where(Epic.epic_key == epic_key)
                )
                epic = result.scalar_one_or_none()
                if not epic:
                    return _err("ENTITY_NOT_FOUND", f"Epic '{epic_key}' not found", 404)

                changes = {}

                # Validate and set new owner
                if new_owner:
                    owner_uuid = uuid.UUID(new_owner)
                    user_check = await db.execute(
                        select(User.id).where(User.id == owner_uuid)
                    )
                    if not user_check.scalar_one_or_none():
                        return _err("ENTITY_NOT_FOUND", f"User {new_owner} not found", 404)
                    old_owner = str(epic.owner_id) if epic.owner_id else None
                    epic.owner_id = owner_uuid
                    changes["owner_id"] = {"old": old_owner, "new": new_owner}

                    # Notify new owner
                    await create_notification(
                        db,
                        user_id=owner_uuid,
                        notification_type="task_assigned",
                        title="Epic-Ownership zugewiesen",
                        body=f"Du bist jetzt Owner von Epic '{epic.title}' ({epic.epic_key}).",
                        link=f"/epics/{epic.epic_key}",
                        entity_type="epic",
                        entity_id=str(epic.id),
                    )

                # Validate and set backup owner
                if new_backup is not None:
                    if new_backup.lower() == "null" or new_backup == "":
                        old_backup = str(epic.backup_owner_id) if epic.backup_owner_id else None
                        epic.backup_owner_id = None
                        changes["backup_owner_id"] = {"old": old_backup, "new": None}
                    else:
                        backup_uuid = uuid.UUID(new_backup)
                        user_check = await db.execute(
                            select(User.id).where(User.id == backup_uuid)
                        )
                        if not user_check.scalar_one_or_none():
                            return _err("ENTITY_NOT_FOUND", f"User {new_backup} not found", 404)
                        old_backup = str(epic.backup_owner_id) if epic.backup_owner_id else None
                        epic.backup_owner_id = backup_uuid
                        changes["backup_owner_id"] = {"old": old_backup, "new": new_backup}

                epic.version += 1
                await db.flush()

                # Audit
                await write_audit(
                    tool_name="reassign_epic_owner",
                    actor_id=actor,
                    actor_role="admin",
                    input_payload={"epic_key": epic_key, "changes": changes},
                    target_id=str(epic.id),
                )

                return _ok({
                    "data": {
                        "epic_key": epic.epic_key,
                        "owner_id": str(epic.owner_id) if epic.owner_id else None,
                        "backup_owner_id": str(epic.backup_owner_id) if epic.backup_owner_id else None,
                        "changes": changes,
                    },
                    "meta": {"version": epic.version},
                })

    except ValueError as ve:
        return _err("VALIDATION_ERROR", str(ve), 422)
    except Exception as exc:
        logger.exception("reassign_epic_owner failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind-list_decision_requests — TASK-6-008
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind-list_decision_requests",
        description=(
            "List decision requests, optionally filtered by state (open, resolved, expired). "
            "Returns id, task_id, epic_id, owner_id, backup_owner_id, state, sla_due_at, "
            "created_at, payload."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "Filter by state: open | resolved | expired",
                },
                "epic_id": {
                    "type": "string",
                    "description": "Filter by epic UUID",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 50)",
                },
            },
        },
    ),
    handler=lambda args: _handle_list_decision_requests(args),
)


async def _handle_list_decision_requests(args: dict) -> list[TextContent]:
    from app.models.decision import DecisionRequest

    try:
        state_filter = (args.get("state") or "").strip() or None
        epic_id = (args.get("epic_id") or "").strip() or None
        limit = min(int(args.get("limit", 50)), 200)

        async with AsyncSessionLocal() as db:
            query = select(DecisionRequest)
            if state_filter:
                query = query.where(DecisionRequest.state == state_filter)
            if epic_id:
                query = query.where(DecisionRequest.epic_id == uuid.UUID(epic_id))
            query = query.order_by(DecisionRequest.sla_due_at.desc()).limit(limit)

            result = await db.execute(query)
            rows = result.scalars().all()

            data = [
                {
                    "id": str(dr.id),
                    "task_id": str(dr.task_id) if dr.task_id else None,
                    "epic_id": str(dr.epic_id) if dr.epic_id else None,
                    "owner_id": str(dr.owner_id) if dr.owner_id else None,
                    "backup_owner_id": str(dr.backup_owner_id) if dr.backup_owner_id else None,
                    "state": dr.state,
                    "sla_due_at": dr.sla_due_at.isoformat() if dr.sla_due_at else None,
                    "payload": dr.payload,
                }
                for dr in rows
            ]

            return _ok({"data": data, "meta": {"count": len(data)}})

    except Exception as exc:
        logger.exception("list_decision_requests failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
