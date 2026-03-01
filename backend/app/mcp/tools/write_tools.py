"""MCP Planer Write-Tools — TASK-4-002.

Architect/Stratege write tools for epic decomposition and task management:
- hivemind/decompose_epic
- hivemind/create_task
- hivemind/create_subtask
- hivemind/link_skill
- hivemind/set_context_boundary
- hivemind/assign_task
- hivemind/update_task_state
"""
from __future__ import annotations

import json
import logging
import uuid

from mcp.types import TextContent, Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _epic_prefix(epic_key: str) -> str:
    """Derive a short task-key prefix from an epic_key.

    Examples:
        EPIC-PHASE-5   → "5"
        EPIC-PHASE-1A  → "1A"
        EPIC-PHASE-F   → "F"
        EPIC-42        → "42"

    Falls back to the raw number after 'EPIC-' if no PHASE pattern.
    """
    import re
    m = re.match(r"EPIC-PHASE-(.+)", epic_key, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    m = re.match(r"EPIC-(\S+)", epic_key, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return epic_key


async def _next_epic_task_key(
    db,
    epic_id: uuid.UUID,
    prefix: str,
) -> str:
    """Generate the next task key for an epic using its prefix.

    Counts existing tasks whose task_key matches TASK-{prefix}-NNN
    and returns the next number, e.g. TASK-5-023.
    """
    from sqlalchemy import func as sa_func, select, text  # noqa: F811
    from app.models.task import Task

    pattern = f"TASK-{prefix}-%"
    result = await db.execute(
        select(sa_func.count()).select_from(Task).where(
            Task.epic_id == epic_id,
            Task.task_key.like(pattern),
        )
    )
    existing_count = result.scalar_one()
    seq = existing_count + 1
    return f"TASK-{prefix}-{seq:03d}"


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


# ── Parameter Alias Normalization ─────────────────────────────────────────────
# Common wrong param names → correct param names.
# Agents frequently use doc-style names (task_id, state, assignee_id)
# instead of the actual schema names (task_key, target_state, user_id).
PARAM_ALIASES: dict[str, str] = {
    "task_id": "task_key",
    "epic_id": "epic_key",
    "parent_task_id": "parent_task_key",
    "state": "target_state",
    "assignee_id": "user_id",
    "new_owner_id": "owner_id",
    "result_text": "result",
    "chosen_option": "decision",
    "blocker": "question",
    "id": "decision_request_id",
}


def normalize_args(args: dict, *, only: set[str] | None = None) -> dict:
    """Apply parameter aliases so common wrong names still work.

    If the canonical name is already present, the alias is ignored.
    If ``only`` is given, only those alias keys are considered.
    """
    out = dict(args)
    for alias, canonical in PARAM_ALIASES.items():
        if only and alias not in only:
            continue
        if alias in out and canonical not in out:
            out[canonical] = out.pop(alias)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/decompose_epic  — split an epic into tasks atomically
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/decompose_epic",
        description=(
            "Decompose an epic into multiple tasks in a single atomic transaction. "
            "All tasks are created with state='incoming' (NOT scoped!). "
            "On any error, the entire batch is rolled back. "
            "After decompose, transition each task: "
            "assign_task → update_task_state(scoped) → update_task_state(ready)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "epic_key": {"type": "string", "description": "The epic key (e.g. 'EPIC-PHASE-4')"},
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "definition_of_done": {"type": "object"},
                            "parent_index": {
                                "type": "integer",
                                "description": "0-based index of parent task in this array (for subtasks)",
                            },
                        },
                        "required": ["title"],
                    },
                    "description": "Array of task definitions to create",
                },
            },
            "required": ["epic_key", "tasks"],
        },
    ),
    handler=lambda args: _handle_decompose_epic(
        normalize_args(args, only={"epic_id"})
    ),
)


async def _handle_decompose_epic(args: dict) -> list[TextContent]:
    from sqlalchemy import select, text

    from app.models.epic import Epic
    from app.models.task import Task

    epic_key = args["epic_key"]
    task_defs = args.get("tasks", [])

    if not task_defs:
        return _err("VALIDATION_ERROR", "At least one task is required")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Resolve epic
                result = await db.execute(select(Epic).where(Epic.epic_key == epic_key))
                epic = result.scalar_one_or_none()
                if not epic:
                    return _err("ENTITY_NOT_FOUND", f"Epic '{epic_key}' not found", 404)

                created_tasks: list[Task] = []
                prefix = _epic_prefix(epic_key)

                for i, td in enumerate(task_defs):
                    # Generate phase-specific task key (TASK-5-001 etc.)
                    task_key = await _next_epic_task_key(db, epic.id, prefix)

                    parent_id = None
                    parent_index = td.get("parent_index")
                    if parent_index is not None:
                        if 0 <= parent_index < len(created_tasks):
                            parent_id = created_tasks[parent_index].id
                        else:
                            return _err(
                                "VALIDATION_ERROR",
                                f"parent_index {parent_index} out of range at task[{i}]",
                            )

                    task = Task(
                        task_key=task_key,
                        external_id=task_key,
                        epic_id=epic.id,
                        title=td["title"],
                        description=td.get("description"),
                        definition_of_done=td.get("definition_of_done"),
                        parent_task_id=parent_id,
                        state="incoming",
                    )
                    db.add(task)
                    await db.flush()
                    await db.refresh(task)
                    created_tasks.append(task)

                return _ok({
                    "data": {
                        "epic_key": epic_key,
                        "tasks_created": len(created_tasks),
                        "task_keys": [t.task_key for t in created_tasks],
                    },
                    "meta": {"atomic": True},
                })
    except Exception as exc:
        logger.exception("decompose_epic failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/create_task  — create a single task in an epic
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/create_task",
        description=(
            "Create a single task within an epic. The task starts with state='incoming'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "epic_key": {"type": "string", "description": "Epic key"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "definition_of_done": {"type": "object"},
                "assigned_to": {"type": "string", "description": "User UUID to assign"},
            },
            "required": ["epic_key", "title"],
        },
    ),
    handler=lambda args: _handle_create_task(args),
)


async def _handle_create_task(args: dict) -> list[TextContent]:
    from sqlalchemy import select, text

    from app.models.epic import Epic
    from app.models.task import Task

    epic_key = args["epic_key"]

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Epic).where(Epic.epic_key == epic_key))
                epic = result.scalar_one_or_none()
                if not epic:
                    return _err("ENTITY_NOT_FOUND", f"Epic '{epic_key}' not found", 404)

                prefix = _epic_prefix(epic_key)
                task_key = await _next_epic_task_key(db, epic.id, prefix)

                assigned_to = None
                if args.get("assigned_to"):
                    assigned_to = uuid.UUID(args["assigned_to"])

                task = Task(
                    task_key=task_key,
                    external_id=task_key,
                    epic_id=epic.id,
                    title=args["title"],
                    description=args.get("description"),
                    definition_of_done=args.get("definition_of_done"),
                    assigned_to=assigned_to,
                    state="incoming",
                )
                db.add(task)
                await db.flush()
                await db.refresh(task)

                return _ok({
                    "data": {
                        "task_key": task.task_key,
                        "id": str(task.id),
                        "epic_key": epic_key,
                        "title": task.title,
                        "state": task.state,
                    },
                    "meta": {"version": task.version},
                })
    except Exception as exc:
        logger.exception("create_task failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/create_subtask  — create a subtask with parent_task_id
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/create_subtask",
        description="Create a subtask linked to a parent task.",
        inputSchema={
            "type": "object",
            "properties": {
                "parent_task_key": {"type": "string", "description": "Parent task key"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "definition_of_done": {"type": "object"},
            },
            "required": ["parent_task_key", "title"],
        },
    ),
    handler=lambda args: _handle_create_subtask(args),
)


async def _handle_create_subtask(args: dict) -> list[TextContent]:
    from sqlalchemy import select, text

    from app.models.task import Task

    parent_key = args["parent_task_key"]

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                result = await db.execute(select(Task).where(Task.task_key == parent_key))
                parent = result.scalar_one_or_none()
                if not parent:
                    return _err("ENTITY_NOT_FOUND", f"Parent task '{parent_key}' not found", 404)

                # Resolve epic to get prefix
                epic_result = await db.execute(select(Epic).where(Epic.id == parent.epic_id))
                epic = epic_result.scalar_one()
                prefix = _epic_prefix(epic.epic_key)
                task_key = await _next_epic_task_key(db, parent.epic_id, prefix)

                subtask = Task(
                    task_key=task_key,
                    external_id=task_key,
                    epic_id=parent.epic_id,
                    parent_task_id=parent.id,
                    title=args["title"],
                    description=args.get("description"),
                    definition_of_done=args.get("definition_of_done"),
                    state="incoming",
                )
                db.add(subtask)
                await db.flush()
                await db.refresh(subtask)

                return _ok({
                    "data": {
                        "task_key": subtask.task_key,
                        "id": str(subtask.id),
                        "parent_task_key": parent_key,
                        "title": subtask.title,
                        "state": subtask.state,
                    },
                    "meta": {"version": subtask.version},
                })
    except Exception as exc:
        logger.exception("create_subtask failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/link_skill  — pin a skill version to a task
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/link_skill",
        description=(
            "Pin a skill (and optionally a specific version) to a task. "
            "Creates a task_skills entry."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string"},
                "skill_id": {"type": "string", "description": "Skill UUID"},
                "pinned_version_id": {
                    "type": "string",
                    "description": "Optional skill_version UUID to pin",
                },
            },
            "required": ["task_key", "skill_id"],
        },
    ),
    handler=lambda args: _handle_link_skill(args),
)


async def _handle_link_skill(args: dict) -> list[TextContent]:
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from app.models.context_boundary import TaskSkill
    from app.models.skill import Skill
    from app.models.task import Task

    task_key = args["task_key"]
    skill_id = uuid.UUID(args["skill_id"])
    pinned = uuid.UUID(args["pinned_version_id"]) if args.get("pinned_version_id") else None

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Verify task
                t_result = await db.execute(select(Task).where(Task.task_key == task_key))
                task = t_result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' not found", 404)

                # Verify skill
                s_result = await db.execute(select(Skill).where(Skill.id == skill_id))
                if not s_result.scalar_one_or_none():
                    return _err("ENTITY_NOT_FOUND", f"Skill '{skill_id}' not found", 404)

                # Upsert task_skill
                stmt = insert(TaskSkill).values(
                    task_id=task.id,
                    skill_id=skill_id,
                    pinned_version_id=pinned,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["task_id", "skill_id"],
                    set_={"pinned_version_id": pinned},
                )
                await db.execute(stmt)

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "skill_id": str(skill_id),
                        "pinned_version_id": str(pinned) if pinned else None,
                    },
                })
    except Exception as exc:
        logger.exception("link_skill failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/set_context_boundary  — set context boundary for a task
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/set_context_boundary",
        description=(
            "Set the context boundary for a task. Defines allowed skills, "
            "allowed docs, and max token budget. Overwrites any previous boundary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string"},
                "allowed_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Skill UUIDs the agent is allowed to use",
                },
                "allowed_docs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Wiki/Doc UUIDs the agent may reference",
                },
                "max_token_budget": {
                    "type": "integer",
                    "description": "Maximum token budget for the task context",
                },
            },
            "required": ["task_key"],
        },
    ),
    handler=lambda args: _handle_set_context_boundary(args),
)


async def _handle_set_context_boundary(args: dict) -> list[TextContent]:
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from app.models.context_boundary import ContextBoundary
    from app.models.task import Task

    task_key = args["task_key"]

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                t_result = await db.execute(select(Task).where(Task.task_key == task_key))
                task = t_result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' not found", 404)

                allowed_skills = [uuid.UUID(s) for s in args.get("allowed_skills", [])]
                allowed_docs = [uuid.UUID(d) for d in args.get("allowed_docs", [])]
                max_tokens = args.get("max_token_budget")

                # Upsert (task_id is unique)
                stmt = insert(ContextBoundary).values(
                    task_id=task.id,
                    allowed_skills=allowed_skills or None,
                    allowed_docs=allowed_docs or None,
                    max_token_budget=max_tokens,
                    set_by=ADMIN_ID,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["task_id"],
                    set_={
                        "allowed_skills": allowed_skills or None,
                        "allowed_docs": allowed_docs or None,
                        "max_token_budget": max_tokens,
                        "set_by": ADMIN_ID,
                    },
                )
                await db.execute(stmt)

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "allowed_skills": len(allowed_skills),
                        "allowed_docs": len(allowed_docs),
                        "max_token_budget": max_tokens,
                    },
                })
    except Exception as exc:
        logger.exception("set_context_boundary failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/assign_task  — assign task to a user
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/assign_task",
        description=(
            "Assign a task to a user. Sets assigned_to (required before scoped→ready). "
            "Triggers a task_assigned notification. "
            "Param is 'user_id' (UUID string), NOT 'assignee_id'. "
            "Param is 'task_key' (e.g. 'TASK-5-001'), NOT 'task_id'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key, e.g. 'TASK-5-001' (NOT task_id)"},
                "user_id": {"type": "string", "description": "UUID of user to assign (NOT assignee_id)"},
            },
            "required": ["task_key", "user_id"],
        },
    ),
    handler=lambda args: _handle_assign_task(
        normalize_args(args, only={"task_id", "assignee_id"})
    ),
)


async def _handle_assign_task(args: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.models.task import Task
    from app.models.user import User
    from app.services.event_bus import publish

    task_key = args["task_key"]
    user_id = uuid.UUID(args["user_id"])

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                t_result = await db.execute(select(Task).where(Task.task_key == task_key))
                task = t_result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' not found", 404)

                # Verify user exists
                u_result = await db.execute(select(User).where(User.id == user_id))
                user = u_result.scalar_one_or_none()
                if not user:
                    return _err("ENTITY_NOT_FOUND", f"User '{user_id}' not found", 404)

                task.assigned_to = user_id
                task.version += 1
                await db.flush()

                # Publish notification
                publish(
                    event_type="task_assigned",
                    data={
                        "task_key": task_key,
                        "task_id": str(task.id),
                        "assigned_to": str(user_id),
                        "assigned_username": user.username,
                        "title": task.title,
                    },
                    channel="notifications",
                )

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "assigned_to": str(user_id),
                        "assigned_username": user.username,
                    },
                    "meta": {"version": task.version},
                })
    except Exception as exc:
        logger.exception("assign_task failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/update_task_state  — architect state transition
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/update_task_state",
        description=(
            "Transition a task to a new state. "
            "Param is 'target_state' (NOT 'state'!). Param is 'task_key' (NOT 'task_id'!). "
            "Happy-path chain: incoming→scoped→ready→in_progress. "
            "Gate: scoped→ready requires assigned_to — call assign_task first! "
            "Gate: in_progress→in_review requires result — call submit_result first! "
            "Gate: in_review→done is BLOCKED — use approve_review instead! "
            "Phase ≥5: all guards must be passed|skipped for in_review."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key, e.g. 'TASK-5-001' (NOT task_id)"},
                "target_state": {"type": "string", "description": "Target state string (NOT 'state'!)"},
                "comment": {"type": "string", "description": "Optional comment"},
            },
            "required": ["task_key", "target_state"],
        },
    ),
    handler=lambda args: _handle_update_task_state(
        normalize_args(args, only={"task_id", "state"})
    ),
)


async def _get_current_phase(db) -> int:
    """Read current_phase from app_settings."""
    from sqlalchemy import text
    result = await db.execute(
        text("SELECT value FROM app_settings WHERE key = 'current_phase'")
    )
    row = result.first()
    return int(row[0]) if row else 1


async def _handle_update_task_state(args: dict) -> list[TextContent]:
    from sqlalchemy import select, update

    from app.models.guard import Guard, TaskGuard
    from app.models.task import Task
    from app.services.state_machine import validate_task_transition

    task_key = args["task_key"]
    target_state = args["target_state"]

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                t_result = await db.execute(select(Task).where(Task.task_key == task_key))
                task = t_result.scalar_one_or_none()
                if not task:
                    return _err("ENTITY_NOT_FOUND", f"Task '{task_key}' not found", 404)

                # Special guard: scoped → ready requires assigned_to
                if task.state == "scoped" and target_state == "ready" and not task.assigned_to:
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        "scoped → ready requires assigned_to. "
                        f"Call hivemind/assign_task first with "
                        f"{{\"task_key\": \"{task_key}\", \"user_id\": \"<uuid>\"}}",
                        422,
                    )

                # ── Phase 5+ Guard Enforcement: in_progress → in_review ──
                if task.state == "in_progress" and target_state == "in_review":
                    current_phase = await _get_current_phase(db)
                    if current_phase >= 5:
                        # Check result is present
                        if not task.result or not task.result.strip():
                            return _err(
                                "REVIEW_GATE_FAILED",
                                "result must be set before in_review. "
                                f"Call hivemind/submit_result first with "
                                f"{{\"task_key\": \"{task_key}\", \"result\": \"<your result text>\"}}",
                                422,
                            )

                        # Check all task_guards are passed or skipped
                        tg_result = await db.execute(
                            select(TaskGuard)
                            .where(TaskGuard.task_id == task.id)
                        )
                        task_guards = tg_result.scalars().all()
                        open_guards = [
                            tg for tg in task_guards
                            if tg.status not in ("passed", "skipped")
                        ]
                        if open_guards:
                            # Fetch guard titles for the error message
                            open_guard_ids = [tg.guard_id for tg in open_guards]
                            g_result = await db.execute(
                                select(Guard).where(Guard.id.in_(open_guard_ids))
                            )
                            guard_map = {g.id: g.title for g in g_result.scalars().all()}
                            open_list = [
                                {
                                    "guard_id": str(tg.guard_id),
                                    "title": guard_map.get(tg.guard_id, "?"),
                                    "status": tg.status,
                                }
                                for tg in open_guards
                            ]
                            return _err(
                                "GUARDS_NOT_PASSED",
                                f"{len(open_guards)} Guards sind noch offen/fehlgeschlagen: "
                                + ", ".join(g["title"] for g in open_list),
                                422,
                            )

                # ── Review-Gate: block direct in_progress → done ──
                if task.state == "in_progress" and target_state == "done":
                    return _err(
                        "REVIEW_GATE_REQUIRED",
                        "Direkte Transition in_progress → done ist nicht erlaubt. "
                        "Zuerst in_review, dann approve_review.",
                        422,
                    )

                # Validate state machine
                validate_task_transition(task.state, target_state)

                old_state = task.state
                task.state = target_state
                task.version += 1
                if args.get("comment"):
                    task.review_comment = args["comment"]

                # ── Guard Reset on qa_failed → in_progress ──
                if old_state == "qa_failed" and target_state == "in_progress":
                    await db.execute(
                        update(TaskGuard)
                        .where(TaskGuard.task_id == task.id)
                        .values(status="pending", result=None, checked_at=None, checked_by=None)
                    )

                await db.flush()

                return _ok({
                    "data": {
                        "task_key": task_key,
                        "previous_state": old_state,
                        "state": target_state,
                    },
                    "meta": {"version": task.version},
                })
    except Exception as exc:
        if hasattr(exc, "status_code"):
            # Re-raise HTTPException from state machine validation
            return _err("INVALID_STATE_TRANSITION", str(exc.detail), exc.status_code)
        logger.exception("update_task_state failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
