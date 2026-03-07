"""MCP Read-Tools: Entity Reads — TASK-3-002.

Tools:
  hivemind-get_epic          — Epic with state, priority, DoD
  hivemind-get_task          — Task with state, assigned_to, pinned_skills, guards
  hivemind-get_skill_versions — Immutable version history of a skill
  hivemind-get_doc           — Epic-Doc by UUID
  hivemind-get_guards        — All guards for a task (global + project + skill + task)
"""
from __future__ import annotations

import json
from mcp.types import TextContent, Tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.models.doc import Doc
from app.models.guard import Guard, TaskGuard
from app.models.skill import Skill, SkillVersion
from app.models.task import Task
from app.models.epic import Epic
from app.services.guard_materialization import materialize_task_guards


# ── Helpers ────────────────────────────────────────────────────────────────

def _json_response(data: dict | list) -> list[TextContent]:
    """Wrap data in a JSON text content response."""
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _not_found(entity: str, key: str) -> list[TextContent]:
    return [TextContent(
        type="text",
        text=json.dumps({"error": {"code": "not_found", "message": f"{entity} '{key}' nicht gefunden."}})
    )]


# ── get_epic ───────────────────────────────────────────────────────────────

async def _handle_get_epic(args: dict) -> list[TextContent]:
    epic_key = args.get("epic_key") or args.get("id", "")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Epic).where(Epic.epic_key == epic_key))
        epic = result.scalar_one_or_none()
        if not epic:
            return _not_found("Epic", epic_key)
        return _json_response({
            "id": str(epic.id),
            "epic_key": epic.epic_key,
            "project_id": str(epic.project_id) if epic.project_id else None,
            "title": epic.title,
            "description": epic.description,
            "state": epic.state,
            "priority": epic.priority,
            "dod_framework": epic.dod_framework,
            "version": epic.version,
            "created_at": str(epic.created_at),
            "updated_at": str(epic.updated_at),
        })


register_tool(
    Tool(
        name="hivemind-get_epic",
        description="Epic mit State, Priority, DoD zurückgeben.",
        inputSchema={
            "type": "object",
            "properties": {
                "epic_key": {"type": "string", "description": "Epic-Key, z.B. 'EPIC-12'"},
            },
            "required": ["epic_key"],
        },
    ),
    _handle_get_epic,
)


# ── get_task ───────────────────────────────────────────────────────────────

async def _handle_get_task(args: dict) -> list[TextContent]:
    task_key = args.get("task_key") or args.get("task_id", "")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Task).where(Task.task_key == task_key))
        task = result.scalar_one_or_none()
        if not task:
            return _not_found("Task", task_key)

        created = await materialize_task_guards(db, task)
        if created:
            await db.commit()

        # Fetch guard summary
        guard_result = await db.execute(
            select(TaskGuard, Guard)
            .join(Guard, TaskGuard.guard_id == Guard.id)
            .where(TaskGuard.task_id == task.id)
        )
        guards = [
            {
                "guard_id": str(tg.guard_id),
                "title": g.title,
                "type": g.type,
                "status": tg.status,
                "skippable": g.skippable,
            }
            for tg, g in guard_result.all()
        ]

        return _json_response({
            "id": str(task.id),
            "task_key": task.task_key,
            "epic_id": str(task.epic_id),
            "title": task.title,
            "description": task.description,
            "state": task.state,
            "assigned_to": str(task.assigned_to) if task.assigned_to else None,
            "pinned_skills": task.pinned_skills,
            "definition_of_done": task.definition_of_done,
            "guards": guards,
            "version": task.version,
            "qa_failed_count": task.qa_failed_count,
            "result": task.result,
            "artifacts": task.artifacts,
            "created_at": str(task.created_at),
            "updated_at": str(task.updated_at),
        })


register_tool(
    Tool(
        name="hivemind-get_task",
        description="Task-Details inkl. State, assigned_to, pinned_skills, Guards-Übersicht.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task-Key, z.B. 'TASK-88'"},
            },
            "required": ["task_key"],
        },
    ),
    _handle_get_task,
)


# ── get_skill_versions ────────────────────────────────────────────────────

async def _handle_get_skill_versions(args: dict) -> list[TextContent]:
    from app.services.key_generator import resolve_skill

    skill_id_raw = args.get("skill_id", "")

    async with AsyncSessionLocal() as db:
        # Resolve by UUID or skill_key (e.g. 'SKILL-7')
        skill = await resolve_skill(db, skill_id_raw)
        if not skill:
            return _not_found("Skill", skill_id_raw)
        skill_id = skill.id

        # Fetch versions
        versions_result = await db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version.desc())
        )
        versions = [
            {
                "id": str(sv.id),
                "skill_id": str(sv.skill_id),
                "version": sv.version,
                "content": sv.content,
                "changed_by": str(sv.changed_by) if sv.changed_by else None,
                "created_at": str(sv.created_at),
            }
            for sv in versions_result.scalars().all()
        ]

        return _json_response({
            "skill_id": str(skill.id),
            "title": skill.title,
            "current_version": skill.version,
            "versions": versions,
        })


register_tool(
    Tool(
        name="hivemind-get_skill_versions",
        description="Immutable Versionshistorie eines Skills.",
        inputSchema={
            "type": "object",
            "properties": {
                "skill_id": {"type": "string", "description": "Skill-Identifier (UUID oder Key, z.B. 'SKILL-7')"},
            },
            "required": ["skill_id"],
        },
    ),
    _handle_get_skill_versions,
)


# ── get_doc ────────────────────────────────────────────────────────────────

async def _handle_get_doc(args: dict) -> list[TextContent]:
    from app.services.key_generator import resolve_doc

    doc_id_raw = args.get("id", "")

    async with AsyncSessionLocal() as db:
        # Resolve by UUID or doc_key (e.g. 'DOC-8')
        doc = await resolve_doc(db, doc_id_raw)
        if not doc:
            return _not_found("Doc", doc_id_raw)
        return _json_response({
            "id": str(doc.id),
            "title": doc.title,
            "content": doc.content,
            "epic_id": str(doc.epic_id) if doc.epic_id else None,
            "version": doc.version,
            "created_at": str(doc.created_at),
            "updated_at": str(doc.updated_at),
        })


register_tool(
    Tool(
        name="hivemind-get_doc",
        description="Epic-Doc laden.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Doc-Identifier (UUID oder Key, z.B. 'DOC-8')"},
            },
            "required": ["id"],
        },
    ),
    _handle_get_doc,
)


# ── get_guards ─────────────────────────────────────────────────────────────

async def _handle_get_guards(args: dict) -> list[TextContent]:
    """Get all guards for a task — global + project + skill + task-level."""
    task_key = args.get("task_key") or args.get("task_id", "")
    async with AsyncSessionLocal() as db:
        task_result = await db.execute(select(Task).where(Task.task_key == task_key))
        task = task_result.scalar_one_or_none()
        if not task:
            return _not_found("Task", task_key)

        # Get epic for project_id
        epic_result = await db.execute(select(Epic).where(Epic.id == task.epic_id))
        epic = epic_result.scalar_one_or_none()
        project_id = epic.project_id if epic else None

        created = await materialize_task_guards(db, task)
        if created:
            await db.commit()

        tg_result = await db.execute(
            select(TaskGuard, Guard)
            .join(Guard, TaskGuard.guard_id == Guard.id)
            .where(TaskGuard.task_id == task.id)
            .order_by(Guard.title.asc())
        )
        guards = [
            {
                "guard_id": str(tg.guard_id),
                "title": g.title,
                "type": g.type,
                "command": g.command,
                "status": tg.status,
                "result": tg.result,
                "skippable": g.skippable,
                "scope": (
                    "skill"
                    if g.skill_id
                    else "project"
                    if project_id and g.project_id == project_id
                    else "global"
                ),
            }
            for tg, g in tg_result.all()
        ]
        return _json_response({
            "task_key": task.task_key,
            "guards": guards,
            "total": len(guards),
        })


register_tool(
    Tool(
        name="hivemind-get_guards",
        description="Alle Guards (global + project + skill + task) für einen Task.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task-Key, z.B. 'TASK-88'"},
            },
            "required": ["task_key"],
        },
    ),
    _handle_get_guards,
)
