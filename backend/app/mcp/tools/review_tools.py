"""MCP Review & Decision Tools — TASK-5-003, TASK-5-004, TASK-5-005, TASK-5-006.

Review and decision management MCP tools:
- hivemind/create_decision_request  — Worker → Blocked (atomic transition)
- hivemind/approve_review           — in_review → done + EXP + epic auto-transition
- hivemind/reject_review            — in_review → qa_failed + comment + count++
- hivemind/reenter_from_qa_failed   — qa_failed → in_progress + guard reset + escalation
- hivemind/cancel_task              — Cancel task from allowed states
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from mcp.types import TextContent, Tool
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.event_bus import publish

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
SLA_HOURS = 72  # Decision request SLA default


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/create_decision_request — TASK-5-003
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/create_decision_request",
        description=(
            "Create a decision request for a task, atomically transitioning it "
            "from in_progress to blocked. Returns 409 if not in_progress. "
            "SLA defaults to 72h. "
            "Param is 'question' (NOT 'blocker'!). "
            "Param is 'task_key' (NOT 'task_id'!)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key, e.g. 'TASK-5-003' (NOT task_id)"},
                "question": {"type": "string", "description": "Decision question for the owner/admin (NOT 'blocker'!)"},
                "context": {"type": "string", "description": "Additional context for the decision"},
                "options": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Possible answer options",
                },
                "sla_hours": {
                    "type": "integer",
                    "description": f"SLA in hours (default: {SLA_HOURS})",
                },
            },
            "required": ["task_key", "question"],
        },
    ),
    handler=lambda args: _handle_create_decision_request(args),
)


async def _handle_create_decision_request(args: dict) -> list[TextContent]:
    from app.models.task import Task
    from app.models.decision import DecisionRequest

    task_key = args.get("task_key") or args.get("task_id", "")
    question = (args.get("question") or args.get("blocker", "")).strip()
    if not question:
        return _err("VALIDATION_ERROR", "question darf nicht leer sein", 422)

    sla_h = args.get("sla_hours", SLA_HOURS)
    options = args.get("options", [])
    context = args.get("context", "")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' nicht gefunden", 404)

                # Task must be in_progress to create a decision request
                if task.state != "in_progress":
                    return _err(
                        "CONFLICT",
                        f"Task '{task_key}' muss in_progress sein, ist '{task.state}'",
                        409,
                    )

                # Atomic transition: in_progress → blocked
                task.state = "blocked"
                task.version += 1

                # Create the decision request
                dr = DecisionRequest(
                    task_id=task.id,
                    epic_id=task.epic_id,
                    owner_id=task.assigned_to,
                    state="open",
                    sla_due_at=datetime.now(timezone.utc) + timedelta(hours=sla_h),
                    payload={
                        "question": question,
                        "context": context,
                        "options": options,
                    },
                )
                db.add(dr)
                await db.flush()
                await db.refresh(dr)

                # Fire SSE event
                publish(
                    "decision_request_created",
                    {
                        "task_key": task_key,
                        "decision_request_id": str(dr.id),
                        "question": question,
                        "sla_due_at": dr.sla_due_at.isoformat(),
                    },
                    channel="tasks",
                )

                return _ok({
                    "data": {
                        "decision_request_id": str(dr.id),
                        "task_key": task_key,
                        "task_state": "blocked",
                        "sla_due_at": dr.sla_due_at.isoformat(),
                    },
                })
    except Exception as exc:
        logger.exception("create_decision_request failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/approve_review — TASK-5-004
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/approve_review",
        description=(
            "Approve a task review: transitions in_review → done. "
            "This is the ONLY way to reach 'done' — do NOT use update_task_state for this! "
            "Awards EXP to the assigned user. Auto-transitions the epic "
            "if all tasks are done. "
            "Param is 'task_key' (NOT 'task_id'!)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key, e.g. 'TASK-5-001' (NOT task_id)"},
                "comment": {"type": "string", "description": "Review approval comment"},
            },
            "required": ["task_key"],
        },
    ),
    handler=lambda args: _handle_approve_review(
        {**(args), **(({"task_key": args.pop("task_id")} if "task_id" in args and "task_key" not in args else {}))}
    ),
)


async def _handle_approve_review(args: dict) -> list[TextContent]:
    from app.models.task import Task
    from app.models.epic import Epic

    task_key = args.get("task_key", "")
    comment = args.get("comment", "Review approved")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' nicht gefunden", 404)

                if task.state != "in_review":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Task muss in_review sein, ist '{task.state}'",
                        422,
                    )

                # Transition in_review → done
                task.state = "done"
                task.version += 1

                # Award EXP (+50 for completing a task)
                exp_awarded = 50
                if task.assigned_to:
                    await _award_exp(db, task.assigned_to, exp_awarded, "task_done", task_key)

                await db.flush()

                # Fire SSE event
                publish(
                    "task_done",
                    {
                        "task_key": task_key,
                        "comment": comment,
                        "exp_awarded": exp_awarded,
                    },
                    channel="tasks",
                )

                # Check epic auto-transition (all tasks done → epic done)
                epic_transitioned = False
                if task.epic_id:
                    epic_transitioned = await _check_epic_completion(db, task.epic_id)

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "state": "done",
                        "exp_awarded": exp_awarded,
                        "epic_auto_transitioned": epic_transitioned,
                        "comment": comment,
                    },
                })
    except Exception as exc:
        logger.exception("approve_review failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/reject_review — TASK-5-004
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/reject_review",
        description=(
            "Reject a task review: transitions in_review → qa_failed. "
            "Increments qa_failed_count and optionally adds a comment."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key"},
                "comment": {"type": "string", "description": "Rejection reason/feedback"},
            },
            "required": ["task_key", "comment"],
        },
    ),
    handler=lambda args: _handle_reject_review(args),
)


async def _handle_reject_review(args: dict) -> list[TextContent]:
    from app.models.task import Task

    task_key = args.get("task_key") or args.get("task_id", "")
    comment = args.get("comment", "").strip()
    if not comment:
        return _err("VALIDATION_ERROR", "comment ist Pflicht bei Ablehnung", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' nicht gefunden", 404)

                if task.state != "in_review":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Task muss in_review sein, ist '{task.state}'",
                        422,
                    )

                # Transition in_review → qa_failed
                task.state = "qa_failed"
                task.qa_failed_count = (task.qa_failed_count or 0) + 1
                task.version += 1

                # Store review comment
                task.review_comment = comment

                await db.flush()

                # Fire SSE event
                publish(
                    "task_qa_failed",
                    {
                        "task_key": task_key,
                        "qa_failed_count": task.qa_failed_count,
                        "comment": comment,
                    },
                    channel="tasks",
                )

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "state": "qa_failed",
                        "qa_failed_count": task.qa_failed_count,
                        "comment": comment,
                    },
                })
    except Exception as exc:
        logger.exception("reject_review failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/reenter_from_qa_failed — TASK-5-005
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/reenter_from_qa_failed",
        description=(
            "Worker re-entry from qa_failed: transitions qa_failed → in_progress. "
            "Resets all guards to pending. Escalates to 'escalated' if "
            "qa_failed_count >= 3."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key"},
            },
            "required": ["task_key"],
        },
    ),
    handler=lambda args: _handle_reenter_from_qa_failed(args),
)


async def _handle_reenter_from_qa_failed(args: dict) -> list[TextContent]:
    from app.models.task import Task
    from app.models.guard import TaskGuard

    task_key = args.get("task_key") or args.get("task_id", "")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' nicht gefunden", 404)

                if task.state != "qa_failed":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Task muss qa_failed sein, ist '{task.state}'",
                        422,
                    )

                # Escalation check: qa_failed_count >= 3 → escalated
                if (task.qa_failed_count or 0) >= 3:
                    task.state = "escalated"
                    task.version += 1
                    await db.flush()

                    publish(
                        "task_escalated",
                        {
                            "task_key": task_key,
                            "qa_failed_count": task.qa_failed_count,
                            "reason": "qa_failed_count >= 3",
                        },
                        channel="tasks",
                    )

                    return _err(
                        "ESCALATED",
                        f"Task '{task_key}' wurde nach {task.qa_failed_count}x QA-Failure eskaliert. "
                        "Manueller Eingriff erforderlich.",
                        422,
                    )

                # Normal re-entry: qa_failed → in_progress
                task.state = "in_progress"
                task.version += 1

                # Reset all guards to pending
                guard_result = await db.execute(
                    select(TaskGuard).where(TaskGuard.task_id == task.id)
                )
                guards = guard_result.scalars().all()
                reset_count = 0
                for tg in guards:
                    if tg.status != "pending":
                        tg.status = "pending"
                        tg.output = None
                        tg.source = None
                        tg.checked_at = None
                        reset_count += 1

                await db.flush()

                publish(
                    "task_reenter",
                    {
                        "task_key": task_key,
                        "guards_reset": reset_count,
                    },
                    channel="tasks",
                )

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "state": "in_progress",
                        "guards_reset": reset_count,
                        "qa_failed_count": task.qa_failed_count,
                    },
                })
    except Exception as exc:
        logger.exception("reenter_from_qa_failed failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/cancel_task — TASK-5-006
# ═══════════════════════════════════════════════════════════════════════════════

CANCELLABLE_STATES = {"incoming", "scoped", "ready", "in_progress", "blocked", "qa_failed", "escalated"}
FORCE_REQUIRED_STATES = {"in_review"}

register_tool(
    Tool(
        name="hivemind/cancel_task",
        description=(
            "Cancel a task. Allowed from most states. "
            "Requires force=true for tasks in_review. "
            "Expires open decision_requests. Checks epic auto-transition."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key"},
                "reason": {"type": "string", "description": "Cancellation reason"},
                "force": {"type": "boolean", "description": "Force cancel in_review/done tasks"},
            },
            "required": ["task_key", "reason"],
        },
    ),
    handler=lambda args: _handle_cancel_task(args),
)


async def _handle_cancel_task(args: dict) -> list[TextContent]:
    from app.models.task import Task
    from app.models.decision import DecisionRequest

    task_key = args.get("task_key") or args.get("task_id", "")
    reason = args.get("reason", "").strip()
    force = args.get("force", False)

    if not reason:
        return _err("VALIDATION_ERROR", "reason ist Pflicht", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' nicht gefunden", 404)

                if task.state == "done":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        "Abgeschlossene Tasks können nicht storniert werden",
                        422,
                    )

                if task.state == "cancelled":
                    return _err("CONFLICT", "Task ist bereits storniert", 409)

                if task.state in FORCE_REQUIRED_STATES and not force:
                    return _err(
                        "FORCE_REQUIRED",
                        f"Task ist in '{task.state}' — force=true erforderlich",
                        422,
                    )

                if task.state not in CANCELLABLE_STATES and task.state not in FORCE_REQUIRED_STATES:
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Task kann im Zustand '{task.state}' nicht storniert werden",
                        422,
                    )

                # Cancel the task
                prev_state = task.state
                task.state = "cancelled"
                task.version += 1
                task.review_comment = f"[Cancelled] {reason}"

                # Expire open decision_requests
                dr_result = await db.execute(
                    select(DecisionRequest)
                    .where(DecisionRequest.task_id == task.id)
                    .where(DecisionRequest.state == "open")
                )
                expired_count = 0
                for dr in dr_result.scalars().all():
                    dr.state = "expired"
                    dr.resolved_at = datetime.now(timezone.utc)
                    expired_count += 1

                await db.flush()

                # Fire SSE event
                publish(
                    "task_cancelled",
                    {
                        "task_key": task_key,
                        "previous_state": prev_state,
                        "reason": reason,
                        "decision_requests_expired": expired_count,
                    },
                    channel="tasks",
                )

                # Check epic auto-transition
                epic_transitioned = False
                if task.epic_id:
                    epic_transitioned = await _check_epic_completion(db, task.epic_id)

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "previous_state": prev_state,
                        "state": "cancelled",
                        "reason": reason,
                        "decision_requests_expired": expired_count,
                        "epic_auto_transitioned": epic_transitioned,
                    },
                })
    except Exception as exc:
        logger.exception("cancel_task failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════════════════════

async def _award_exp(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
    trigger: str,
    entity_key: str,
) -> None:
    """Award EXP to a user via users.exp_points.

    Simple increment — non-critical, failures are logged but do not
    propagate to the caller.
    """
    from app.models.user import User

    try:
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            user.exp_points = (user.exp_points or 0) + amount
            await db.flush()
    except Exception:
        # EXP is non-critical — don't fail the main operation
        logger.exception("_award_exp failed (non-critical)")


async def _check_epic_completion(db: AsyncSession, epic_id: uuid.UUID) -> bool:
    """Check if all tasks of an epic are done, and auto-transition epic to done."""
    from app.models.task import Task
    from app.models.epic import Epic

    try:
        # Count tasks not in 'done' or 'cancelled' state
        result = await db.execute(
            select(sa_func.count(Task.id))
            .where(Task.epic_id == epic_id)
            .where(Task.state.notin_(["done", "cancelled"]))
        )
        remaining = result.scalar()

        if remaining == 0:
            # All tasks done/cancelled — transition epic
            e_result = await db.execute(select(Epic).where(Epic.id == epic_id))
            epic = e_result.scalar_one_or_none()
            if epic and epic.state != "done":
                epic.state = "done"
                epic.version += 1
                await db.flush()
                publish(
                    "epic_done",
                    {"epic_key": epic.epic_key, "epic_id": str(epic_id)},
                    channel="epics",
                )
                return True
        return False
    except Exception:
        logger.exception("_check_epic_completion failed (non-critical)")
        return False
