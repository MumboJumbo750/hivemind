"""MCP Prompt-Capability — TASK-IDE-002.

Exposes agent-role prompts as MCP Prompts (MCP Prompt-Capability).
In VS Code Copilot Chat, prompts appear as slash-commands: /hivemind.worker, /hivemind.next etc.

Registered prompts:
  hivemind.worker     — Worker-Prompt für aktiven Task (arg: task_key)
  hivemind.kartograph — Kartograph-Prompt (arg: task_key, optional)
  hivemind.reviewer   — Review-Prompt für Task in in_review (arg: task_key)
  hivemind.gaertner   — Gaertner-Prompt nach Task-Done (arg: task_key)
  hivemind.stratege   — Stratege-Prompt für Epic-Planung (arg: project_id)
  hivemind.architekt  — Architekt-Prompt für Epic-Zerlegung (arg: epic_id)
  hivemind.next       — Nächster anstehender Prompt (auto-detect, keine Args)
"""
from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import server
from app.models.conductor import ConductorDispatch
from app.models.context_boundary import ContextBoundary, TaskSkill
from app.models.epic import Epic
from app.models.project import Project
from app.models.skill import Skill
from app.models.task import Task
from app.services.prompt_generator import PromptGenerator
from mcp.types import (
    EmbeddedResource,
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    TextContent,
    TextResourceContents,
)

logger = logging.getLogger(__name__)

# ── Prompt Definitions ──────────────────────────────────────────────────────

_PROMPTS: list[Prompt] = [
    Prompt(
        name="hivemind.worker",
        description="Worker-Prompt: Implementierungs-Auftrag für einen Task. task_key ist Pflicht.",
        arguments=[
            PromptArgument(name="task_key", description="Task-Key (z.B. TASK-42)", required=True),
        ],
    ),
    Prompt(
        name="hivemind.reviewer",
        description="Reviewer-Prompt: Review-Auftrag für einen Task in in_review.",
        arguments=[
            PromptArgument(name="task_key", description="Task-Key des zu reviewenden Tasks", required=True),
        ],
    ),
    Prompt(
        name="hivemind.gaertner",
        description="Gaertner-Prompt: Skill-Harvest nach Task-Abschluss.",
        arguments=[
            PromptArgument(name="task_key", description="Task-Key des abgeschlossenen Tasks", required=True),
        ],
    ),
    Prompt(
        name="hivemind.kartograph",
        description="Kartograph-Prompt: Code-Exploration (Bootstrap oder Follow-Up).",
        arguments=[
            PromptArgument(name="task_key", description="Task-Key (optional — für Follow-Up)", required=False),
        ],
    ),
    Prompt(
        name="hivemind.stratege",
        description="Stratege-Prompt: Epic-Planung für ein Projekt.",
        arguments=[
            PromptArgument(name="project_id", description="Projekt-UUID", required=False),
        ],
    ),
    Prompt(
        name="hivemind.architekt",
        description="Architekt-Prompt: Epic-Zerlegung in Tasks.",
        arguments=[
            PromptArgument(name="epic_id", description="Epic-Key (z.B. EPIC-12)", required=False),
        ],
    ),
    Prompt(
        name="hivemind.next",
        description="Nächster anstehender Prompt — auto-detect: in_review → Worker, scoped → Worker, etc.",
        arguments=[],
    ),
]

# Map prompt name → (prompt_type, task_field)
_ROLE_MAP = {
    "hivemind.worker": ("worker", "task_key"),
    "hivemind.reviewer": ("review", "task_key"),
    "hivemind.gaertner": ("gaertner", "task_key"),
    "hivemind.kartograph": ("kartograph", "task_key"),
    "hivemind.stratege": ("stratege", "project_id"),
    "hivemind.architekt": ("architekt", "epic_id"),
}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")


def _task_resource_uri(task_key: str) -> str:
    return f"hivemind://task/{task_key}"


def _context_boundary_resource_uri(task_key: str) -> str:
    return f"hivemind://context-boundary/{task_key}"


def _skill_resource_uri(title: str) -> str:
    return f"hivemind://skill/{_slugify(title)}"


def _is_uuid(raw: str | None) -> bool:
    if not raw:
        return False
    try:
        uuid.UUID(str(raw))
        return True
    except ValueError:
        return False


def _resource_message(uri: str, text: str, mime_type: str) -> PromptMessage:
    return PromptMessage(
        role="user",
        content=EmbeddedResource(
            type="resource",
            resource=TextResourceContents(uri=uri, mimeType=mime_type, text=text),
        ),
    )


async def _load_task_resource_message(db: AsyncSession, task_key: str) -> tuple[PromptMessage | None, Task | None]:
    result = await db.execute(select(Task).where(Task.task_key == task_key))
    task = result.scalar_one_or_none()
    if task is None:
        return None, None
    cb_row = await db.execute(select(ContextBoundary).where(ContextBoundary.task_id == task.id).limit(1))
    cb = cb_row.scalar_one_or_none()
    task_payload = json.dumps(
        {
            "task_key": task.task_key,
            "title": task.title,
            "description": task.description,
            "state": task.state,
            "definition_of_done": task.definition_of_done,
            "pinned_skills": task.pinned_skills,
            "context_boundary": (
                {
                    "resource_uri": _context_boundary_resource_uri(task.task_key),
                    "allowed_skills": [str(skill_id) for skill_id in (cb.allowed_skills or [])],
                    "allowed_docs": [str(doc_id) for doc_id in (cb.allowed_docs or [])],
                    "external_access": cb.external_access,
                    "max_token_budget": cb.max_token_budget,
                    "version": cb.version,
                }
                if cb
                else None
            ),
        },
        default=str,
        ensure_ascii=False,
    )
    return _resource_message(_task_resource_uri(task.task_key), task_payload, "application/json"), task


async def _load_worker_skill_messages(db: AsyncSession, task: Task) -> list[PromptMessage]:
    messages: list[PromptMessage] = []
    linked_skills = (
        await db.execute(
            select(Skill.title, Skill.content)
            .join(TaskSkill, TaskSkill.skill_id == Skill.id)
            .where(TaskSkill.task_id == task.id)
            .order_by(Skill.title.asc())
            .limit(8)
        )
    ).all()

    for title, content in linked_skills:
        messages.append(_resource_message(_skill_resource_uri(title), content, "text/markdown"))

    if messages:
        return messages

    for skill_ref in (task.pinned_skills or [])[:8]:
        skill_name = str(skill_ref)
        messages.append(
            _resource_message(
                _skill_resource_uri(skill_name),
                f"Pinned skill reference from task context: {skill_name}",
                "text/plain",
            )
        )
    return messages


async def _load_context_boundary_resource_message(db: AsyncSession, task: Task) -> PromptMessage | None:
    row = await db.execute(select(ContextBoundary).where(ContextBoundary.task_id == task.id).limit(1))
    cb = row.scalar_one_or_none()
    if cb is None:
        return None
    payload = json.dumps(
        {
            "task_key": task.task_key,
            "allowed_skills": [str(skill_id) for skill_id in (cb.allowed_skills or [])],
            "allowed_docs": [str(doc_id) for doc_id in (cb.allowed_docs or [])],
            "external_access": cb.external_access,
            "max_token_budget": cb.max_token_budget,
            "version": cb.version,
            "set_by": str(cb.set_by),
            "created_at": cb.created_at.isoformat() if cb.created_at else None,
        },
        default=str,
        ensure_ascii=False,
    )
    return _resource_message(_context_boundary_resource_uri(task.task_key), payload, "application/json")


# ── Helper: find next pending dispatch ─────────────────────────────────────

def _normalize_dispatch_prompt_type(agent_role: str | None, prompt_type: str | None) -> str | None:
    if agent_role == "reviewer":
        return "review"
    if agent_role in {"worker", "gaertner", "kartograph", "stratege", "architekt"}:
        return agent_role

    if not prompt_type:
        return None
    prefix = prompt_type.split("_", 1)[0].strip().lower()
    if prefix == "reviewer":
        return "review"
    if prefix in {"worker", "gaertner", "kartograph", "stratege", "architekt"}:
        return prefix
    return None


async def _lookup_task_key(db: AsyncSession, ref: str | None) -> str | None:
    if not ref:
        return None
    row = await db.execute(select(Task.task_key).where(Task.task_key == ref).limit(1))
    task_key = row.scalar_one_or_none()
    if task_key:
        return task_key
    if not _is_uuid(ref):
        return None
    row = await db.execute(select(Task.task_key).where(Task.id == uuid.UUID(ref)).limit(1))
    return row.scalar_one_or_none()


async def _lookup_epic_key(db: AsyncSession, ref: str | None) -> str | None:
    if not ref:
        return None
    row = await db.execute(select(Epic.epic_key).where(Epic.epic_key == ref).limit(1))
    epic_key = row.scalar_one_or_none()
    if epic_key:
        return epic_key
    if _is_uuid(ref):
        row = await db.execute(select(Epic.epic_key).where(Epic.id == uuid.UUID(ref)).limit(1))
        epic_key = row.scalar_one_or_none()
        if epic_key:
            return epic_key
    # Fallback: treat ref as task key and resolve to owning epic.
    row = await db.execute(
        select(Epic.epic_key)
        .join(Task, Task.epic_id == Epic.id)
        .where(Task.task_key == ref)
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _lookup_project_id(db: AsyncSession, ref: str | None) -> str | None:
    if not ref:
        return None
    if _is_uuid(ref):
        uid = uuid.UUID(ref)
        row = await db.execute(select(Project.id).where(Project.id == uid).limit(1))
        project_id = row.scalar_one_or_none()
        if project_id:
            return str(project_id)

        row = await db.execute(select(Epic.project_id).where(Epic.id == uid).limit(1))
        epic_project_id = row.scalar_one_or_none()
        if epic_project_id:
            return str(epic_project_id)

    row = await db.execute(select(Epic.project_id).where(Epic.epic_key == ref).limit(1))
    epic_project_id = row.scalar_one_or_none()
    if epic_project_id:
        return str(epic_project_id)
    return None


async def _resolve_dispatch_args(
    db: AsyncSession,
    *,
    prompt_type: str,
    trigger_id: str,
) -> tuple[str | None, str | None, str | None]:
    task_id: str | None = None
    epic_id: str | None = None
    project_id: str | None = None

    if prompt_type in {"worker", "review"}:
        task_id = await _lookup_task_key(db, trigger_id)
    elif prompt_type == "gaertner":
        task_id = await _lookup_task_key(db, trigger_id)
        if not task_id:
            epic_id = await _lookup_epic_key(db, trigger_id)
    elif prompt_type == "architekt":
        epic_id = await _lookup_epic_key(db, trigger_id)
    elif prompt_type == "stratege":
        project_id = await _lookup_project_id(db, trigger_id)

    return task_id, epic_id, project_id


def _has_required_args(prompt_type: str, task_id: str | None, epic_id: str | None, project_id: str | None) -> bool:
    if prompt_type in {"worker", "review"}:
        return bool(task_id)
    if prompt_type == "gaertner":
        return bool(task_id or epic_id)
    if prompt_type == "architekt":
        return bool(epic_id)
    if prompt_type == "stratege":
        return bool(project_id)
    return True


async def _find_next() -> tuple[str, str | None, str | None, str | None, str]:
    """Return (prompt_type, task_id, epic_id, project_id, description)."""
    async with AsyncSessionLocal() as db:
        # 1) Prefer open IDE dispatches from conductor queue.
        rows = await db.execute(
            select(ConductorDispatch)
            .where(
                ConductorDispatch.execution_mode == "ide",
                ConductorDispatch.status.in_(["dispatched", "acknowledged", "running"]),
            )
            .order_by(ConductorDispatch.dispatched_at.asc())
            .limit(20)
        )
        for dispatch in rows.scalars():
            prompt_type = _normalize_dispatch_prompt_type(dispatch.agent_role, dispatch.prompt_type)
            if not prompt_type:
                continue
            task_id, epic_id, project_id = await _resolve_dispatch_args(
                db,
                prompt_type=prompt_type,
                trigger_id=dispatch.trigger_id,
            )
            if not _has_required_args(prompt_type, task_id, epic_id, project_id):
                continue
            return (
                prompt_type,
                task_id,
                epic_id,
                project_id,
                f"Nächster Dispatch: [{prompt_type.upper()}] {dispatch.trigger_id}",
            )

        # 2) Fallback heuristic when no open dispatch exists.
        row = await db.execute(
            select(Task.task_key).where(Task.state == "in_review").order_by(Task.updated_at).limit(1)
        )
        task_key = row.scalar_one_or_none()
        if task_key:
            return "review", task_key, None, None, f"Nächster Dispatch: [REVIEW] {task_key}"

        row = await db.execute(
            select(Task.task_key).where(Task.state == "scoped").order_by(Task.updated_at).limit(1)
        )
        task_key = row.scalar_one_or_none()
        if task_key:
            return "worker", task_key, None, None, f"Nächster Dispatch: [WORKER] {task_key}"

        row = await db.execute(
            select(Skill.id).where(Skill.lifecycle.in_(["draft", "pending_merge"])).limit(1)
        )
        if row.scalar_one_or_none():
            return "gaertner", None, None, None, "Nächster Dispatch: [GAERTNER] Skill-Proposal"

    return "kartograph", None, None, None, "Nächster Dispatch: [KARTOGRAPH] —"


# ── MCP Prompt Handlers ─────────────────────────────────────────────────────

@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """Return all registered Hivemind agent prompts."""
    return _PROMPTS


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
    """Generate and return a Hivemind agent prompt."""
    args = arguments or {}

    try:
        if name == "hivemind.next":
            prompt_type, task_id, epic_id, project_id, description = await _find_next()
        elif name in _ROLE_MAP:
            prompt_type, field = _ROLE_MAP[name]
            task_id = args.get("task_key") if field == "task_key" else None
            epic_id = args.get("epic_id") if field == "epic_id" else None
            project_id = args.get("project_id") if field == "project_id" else None
            description = f"Hivemind {prompt_type.capitalize()}-Prompt"
        else:
            return GetPromptResult(
                description="Unbekannter Prompt",
                messages=[PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=f"Unbekannter Prompt: {name}"),
                )],
            )

        async with AsyncSessionLocal() as db:
            generator = PromptGenerator(db)
            prompt_text = await generator.generate(
                prompt_type,
                task_id=task_id,
                epic_id=epic_id,
                project_id=project_id,
            )
            messages: list[PromptMessage] = [
                PromptMessage(
                    role="user",
                    content=TextContent(type="text", text=prompt_text),
                )
            ]

            # Agent Mode integration: /hivemind.worker auto-loads task + skill resources.
            if prompt_type == "worker" and task_id:
                task_resource_msg, task = await _load_task_resource_message(db, task_id)
                if task_resource_msg:
                    messages.append(task_resource_msg)
                if task:
                    messages.extend(await _load_worker_skill_messages(db, task))
                    context_boundary_msg = await _load_context_boundary_resource_message(db, task)
                    if context_boundary_msg:
                        messages.append(context_boundary_msg)
            elif prompt_type == "review" and task_id:
                task_resource_msg, task = await _load_task_resource_message(db, task_id)
                if task_resource_msg:
                    messages.append(task_resource_msg)
                if task:
                    context_boundary_msg = await _load_context_boundary_resource_message(db, task)
                    if context_boundary_msg:
                        messages.append(context_boundary_msg)

            await db.commit()

        return GetPromptResult(
            description=description,
            messages=messages,
        )

    except Exception as exc:
        logger.exception("MCP Prompt generation failed: %s", name)
        return GetPromptResult(
            description=f"Fehler beim Generieren: {exc}",
            messages=[PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=f"Prompt-Generierung fehlgeschlagen: {exc}\n\nBitte Backend-Logs prüfen.",
                ),
            )],
        )
