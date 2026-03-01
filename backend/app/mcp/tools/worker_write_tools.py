"""MCP Worker Write-Tools — TASK-5-001.

Worker agent tools for task execution:
- hivemind/submit_result      — Save result + artifacts on a task (state stays in_progress)
- hivemind/report_guard_result — Report guard check outcome (passed|failed|skipped)
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

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/submit_result  — save result + artifacts (state stays in_progress)
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/submit_result",
        description=(
            "Save a worker's result and artifacts on a task. "
            "The task state remains in_progress (this tool does NOT change state!). "
            "NEXT STEP: call hivemind/update_task_state with target_state='in_review'. "
            "Param is 'result' (NOT 'result_text'!). "
            "Param is 'task_key' (NOT 'task_id'!). "
            "Idempotent: calling again overwrites result/artifacts."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {
                    "type": "string",
                    "description": "Task key, e.g. 'TASK-5-001' (NOT task_id)",
                },
                "result": {
                    "type": "string",
                    "description": "Text result of the worker's work (NOT result_text!)",
                },
                "artifacts": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "JSON array of artifact objects (files, links, etc.)",
                },
            },
            "required": ["task_key", "result"],
        },
    ),
    handler=lambda args: _handle_submit_result(args),
)


async def _handle_submit_result(args: dict) -> list[TextContent]:
    from app.models.task import Task

    # Normalize common alias mistakes
    if "task_id" in args and "task_key" not in args:
        args["task_key"] = args.pop("task_id")
    if "result_text" in args and "result" not in args:
        args["result"] = args.pop("result_text")

    task_key = args["task_key"]
    result_text = args.get("result", "").strip()
    artifacts = args.get("artifacts", [])

    if not result_text:
        return _err("VALIDATION_ERROR",
                    "'result' param must not be empty (did you use 'result_text'? The correct param name is 'result').",
                    422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                t_result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = t_result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' nicht gefunden", 404)

                # Task must be in_progress to submit results
                if task.state != "in_progress":
                    return _err(
                        "INVALID_STATE",
                        f"Task muss in_progress sein, ist aber '{task.state}'",
                        409,
                    )

                # Idempotent: overwrite result + artifacts
                task.result = result_text
                task.artifacts = artifacts
                task.version += 1
                await db.flush()

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "state": task.state,
                        "result_length": len(result_text),
                        "artifacts_count": len(artifacts),
                    },
                    "meta": {"version": task.version},
                })
    except Exception as exc:
        logger.exception("submit_result failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/report_guard_result  — report guard check outcome
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/report_guard_result",
        description=(
            "Report the result of a guard check for a task. "
            "Sets task_guards.status to passed|failed|skipped with a result text. "
            "Source is always 'self-reported'. "
            "skippable=false guards cannot be skipped (422)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {
                    "type": "string",
                    "description": "Task key, e.g. 'TASK-5-001'",
                },
                "guard_id": {
                    "type": "string",
                    "description": "UUID of the guard to report on",
                },
                "status": {
                    "type": "string",
                    "enum": ["passed", "failed", "skipped"],
                    "description": "Guard check result",
                },
                "result": {
                    "type": "string",
                    "description": "Textual result/output of the guard check (required)",
                },
            },
            "required": ["task_key", "guard_id", "status", "result"],
        },
    ),
    handler=lambda args: _handle_report_guard_result(args),
)


async def _handle_report_guard_result(args: dict) -> list[TextContent]:
    from app.models.guard import Guard, TaskGuard
    from app.models.task import Task

    task_key = args["task_key"]

    try:
        guard_id = uuid.UUID(args["guard_id"])
    except (KeyError, ValueError) as exc:
        return _err("VALIDATION_ERROR", f"Ungültige guard_id: {exc}", 422)

    status = args.get("status", "")
    if status not in ("passed", "failed", "skipped"):
        return _err("VALIDATION_ERROR", f"status muss passed|failed|skipped sein, ist '{status}'", 422)

    result_text = args.get("result", "").strip()
    if not result_text:
        return _err("VALIDATION_ERROR", "'result' param for guard check output must not be empty.", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Verify task exists and is in_progress
                t_result = await db.execute(
                    select(Task).where(Task.task_key == task_key)
                )
                task = t_result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' nicht gefunden", 404)

                if task.state != "in_progress":
                    return _err(
                        "INVALID_STATE",
                        f"Task muss in_progress sein, ist aber '{task.state}'",
                        409,
                    )

                # Find the task_guard for this task+guard combo
                tg_result = await db.execute(
                    select(TaskGuard)
                    .where(TaskGuard.task_id == task.id, TaskGuard.guard_id == guard_id)
                )
                task_guard = tg_result.scalar_one_or_none()
                if not task_guard:
                    return _err(
                        "ENTITY_NOT_FOUND",
                        f"TaskGuard für Task '{task_key}' und Guard '{guard_id}' nicht gefunden",
                        404,
                    )

                # Check skippable constraint
                if status == "skipped":
                    g_result = await db.execute(
                        select(Guard).where(Guard.id == guard_id)
                    )
                    guard = g_result.scalar_one_or_none()
                    if guard and not guard.skippable:
                        return _err(
                            "GUARD_NOT_SKIPPABLE",
                            f"Guard '{guard.title}' ist nicht überspringbar (skippable=false)",
                            422,
                        )

                # Update task_guard
                task_guard.status = status
                task_guard.result = result_text
                task_guard.checked_at = datetime.now(timezone.utc)
                task_guard.checked_by = ADMIN_ID  # Solo-mode
                await db.flush()

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "guard_id": str(guard_id),
                        "status": status,
                        "result": result_text,
                        "checked_at": str(task_guard.checked_at),
                        "source": "self-reported",
                    },
                })
    except Exception as exc:
        logger.exception("report_guard_result failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
