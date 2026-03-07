"""MCP Resource capability for Hivemind context resources."""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any
from urllib.parse import unquote

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.mcp.server import server
from app.models.context_boundary import ContextBoundary, TaskSkill
from app.models.epic import Epic
from app.models.guard import Guard, TaskGuard
from app.models.project import Project
from app.models.skill import Skill
from app.models.task import Task
from app.models.wiki import WikiArticle
from app.services.guard_materialization import materialize_task_guards
from app.services.prompt_generator import PromptGenerator
from mcp.types import Resource

logger = logging.getLogger(__name__)

_MIME_JSON = "application/json"
_MIME_TEXT = "text/plain"
_MIME_MD = "text/markdown"
_PROMPT_ROLES = ("worker", "reviewer", "gaertner", "kartograph", "stratege", "architekt", "triage")
_CLOSED_STATES = ("done", "cancelled")


def _slugify(text: str) -> str:
    from app.services.key_generator import slugify
    return slugify(text)


def _parse_resource_uri(uri: str) -> tuple[str, str]:
    match = re.match(r"^hivemind://([^/]+)(?:/(.+))?$", uri)
    if not match:
        raise ValueError(f"Ungültige Resource-URI: {uri}")
    res_type = match.group(1)
    res_id = unquote(match.group(2) or "")
    return res_type, res_id


def _task_uri(task_key: str) -> str:
    return f"hivemind://task/{task_key}"


def _epic_uri(epic_ref: str) -> str:
    return f"hivemind://epic/{epic_ref}"


def _wiki_uri(slug: str) -> str:
    return f"hivemind://wiki/{slug}"


def _skill_uri(skill_title: str) -> str:
    return f"hivemind://skill/{_slugify(skill_title)}"


def _context_boundary_uri(task_key: str) -> str:
    return f"hivemind://context-boundary/{task_key}"


def _prompt_uri(role: str) -> str:
    return f"hivemind://prompt/{role}"


def _health_report_uri() -> str:
    return "hivemind://health-report"


def _task_state_priority():
    return case(
        (Task.state == "qa_failed", 0),
        (Task.state == "in_progress", 1),
        (Task.state == "in_review", 2),
        (Task.state == "blocked", 3),
        (Task.state == "scoped", 4),
        (Task.state == "ready", 5),
        (Task.state == "incoming", 6),
        else_=99,
    )


def _epic_state_priority():
    return case(
        (Epic.state == "blocked", 0),
        (Epic.state == "in_progress", 1),
        (Epic.state == "review", 2),
        (Epic.state == "ready", 3),
        (Epic.state == "incoming", 4),
        else_=99,
    )


def _infer_epic_dependencies(epic_key: str) -> list[str]:
    match = re.match(r"^(.*?)(\d+)$", epic_key)
    if not match:
        return []
    prefix, raw_num = match.groups()
    current = int(raw_num)
    if current <= 1:
        return []
    prev_num = str(current - 1).zfill(len(raw_num))
    return [f"{prefix}{prev_num}"]


async def _find_latest_health_report(db: AsyncSession) -> Task | None:
    row = await db.execute(
        select(Task)
        .where(
            Task.task_key.like("TASK-HEALTH-%"),
            Task.result.is_not(None),
        )
        .order_by(Task.updated_at.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


async def _resolve_prompt_args(db: AsyncSession, role: str) -> tuple[str, dict[str, str], str | None]:
    prompt_type = "review" if role == "reviewer" else role
    if prompt_type in {"kartograph", "triage"}:
        return prompt_type, {}, None

    if prompt_type == "worker":
        row = await db.execute(
            select(Task.task_key)
            .where(Task.state.in_(["qa_failed", "in_progress", "scoped", "ready", "incoming"]))
            .order_by(_task_state_priority(), Task.updated_at.desc())
            .limit(1)
        )
        task_key = row.scalar_one_or_none()
        if task_key:
            return prompt_type, {"task_id": task_key}, None
        return prompt_type, {}, "Kein offener Task für worker-Prompt gefunden."

    if prompt_type == "review":
        row = await db.execute(
            select(Task.task_key)
            .where(Task.state == "in_review")
            .order_by(Task.updated_at.desc())
            .limit(1)
        )
        task_key = row.scalar_one_or_none()
        if task_key:
            return prompt_type, {"task_id": task_key}, None
        return prompt_type, {}, "Kein Task in `in_review` für reviewer-Prompt gefunden."

    if prompt_type == "gaertner":
        row = await db.execute(
            select(Task.task_key)
            .where(Task.state == "done", Task.result.is_not(None))
            .order_by(Task.updated_at.desc())
            .limit(1)
        )
        task_key = row.scalar_one_or_none()
        if task_key:
            return prompt_type, {"task_id": task_key}, None
        return prompt_type, {}, "Kein abgeschlossener Task mit Ergebnis für gaertner-Prompt gefunden."

    if prompt_type == "architekt":
        row = await db.execute(
            select(Epic.epic_key)
            .where(Epic.state.notin_(_CLOSED_STATES))
            .order_by(_epic_state_priority(), Epic.updated_at.desc())
            .limit(1)
        )
        epic_key = row.scalar_one_or_none()
        if epic_key:
            return prompt_type, {"epic_id": epic_key}, None
        return prompt_type, {}, "Kein offenes Epic für architekt-Prompt gefunden."

    if prompt_type == "stratege":
        row = await db.execute(select(Project.id).order_by(Project.created_at.desc()).limit(1))
        project_id = row.scalar_one_or_none()
        if project_id:
            return prompt_type, {"project_id": str(project_id)}, None
        return prompt_type, {}, "Kein Projekt für stratege-Prompt gefunden."

    return prompt_type, {}, f"Unbekannte Rolle: {role}"


@server.list_resources()
async def list_resources() -> list[Resource]:
    """Return dynamic MCP resource list based on current repository state."""
    resources: list[Resource] = []

    async with AsyncSessionLocal() as db:
        task_rows = (
            await db.execute(
                select(Task.task_key, Task.title, Task.state)
                .where(Task.state.notin_(_CLOSED_STATES))
                .order_by(_task_state_priority(), Task.updated_at.desc())
                .limit(25)
            )
        ).all()
        for task_key, title, state in task_rows:
            resources.append(
                Resource(
                    uri=_task_uri(task_key),  # type: ignore[arg-type]
                    name=f"Open Task: {task_key} - {title}",
                    description=f"State: {state}",
                    mimeType=_MIME_JSON,
                )
            )

        epic_rows = (
            await db.execute(
                select(Epic.id, Epic.epic_key, Epic.title, Epic.state)
                .where(Epic.state.notin_(_CLOSED_STATES))
                .order_by(_epic_state_priority(), Epic.updated_at.desc())
                .limit(12)
            )
        ).all()
        for epic_id, epic_key, title, state in epic_rows:
            resources.append(
                Resource(
                    uri=_epic_uri(str(epic_id)),  # type: ignore[arg-type]
                    name=f"Epic: {epic_key} - {title}",
                    description=f"State: {state}",
                    mimeType=_MIME_JSON,
                )
            )

        boundary_rows = (
            await db.execute(
                select(Task.task_key)
                .join(ContextBoundary, ContextBoundary.task_id == Task.id)
                .where(Task.state.notin_(_CLOSED_STATES))
                .order_by(Task.updated_at.desc())
                .limit(10)
            )
        ).scalars()
        for task_key in boundary_rows:
            resources.append(
                Resource(
                    uri=_context_boundary_uri(task_key),  # type: ignore[arg-type]
                    name=f"Context Boundary: {task_key}",
                    description="Task scope, allowed skills/docs, token budget",
                    mimeType=_MIME_JSON,
                )
            )

        wiki_rows = (
            await db.execute(
                select(WikiArticle.slug, WikiArticle.title)
                .where(WikiArticle.deleted_at.is_(None))
                .order_by(WikiArticle.updated_at.desc())
                .limit(20)
            )
        ).all()
        for slug, title in wiki_rows:
            resources.append(
                Resource(
                    uri=_wiki_uri(slug),  # type: ignore[arg-type]
                    name=f"Wiki: {title}",
                    mimeType=_MIME_MD,
                )
            )

        skill_rows = (
            await db.execute(
                select(Skill.title, Skill.lifecycle)
                .where(Skill.deleted_at.is_(None))
                .order_by(
                    case((Skill.lifecycle == "active", 0), (Skill.lifecycle == "pending_merge", 1), else_=2),
                    Skill.updated_at.desc(),
                )
                .limit(30)
            )
        ).all()
        for title, lifecycle in skill_rows:
            resources.append(
                Resource(
                    uri=_skill_uri(title),  # type: ignore[arg-type]
                    name=f"Skill: {title}",
                    description=f"Lifecycle: {lifecycle}",
                    mimeType=_MIME_MD,
                )
            )

        health_report_task = await _find_latest_health_report(db)
        if health_report_task:
            resources.append(
                Resource(
                    uri=_health_report_uri(),  # type: ignore[arg-type]
                    name="Repo Health Report",
                    description=f"Latest: {health_report_task.task_key}",
                    mimeType=_MIME_MD,
                )
            )

    for role in _PROMPT_ROLES:
        resources.append(
            Resource(
                uri=_prompt_uri(role),  # type: ignore[arg-type]
                name=f"Prompt: {role}",
                description=f"Generated prompt resource for role '{role}'",
                mimeType=_MIME_TEXT,
            )
        )

    return resources


async def _read_task_resource(db: AsyncSession, task_key: str) -> str:
    task_row = await db.execute(select(Task).where(Task.task_key == task_key))
    task = task_row.scalar_one_or_none()
    if not task:
        return json.dumps({"error": f"Task nicht gefunden: {task_key}"})

    await materialize_task_guards(db, task)

    guard_rows = (
        await db.execute(
            select(Guard.title, Guard.type, Guard.command, Guard.skippable, TaskGuard.status, TaskGuard.result)
            .join(TaskGuard, TaskGuard.guard_id == Guard.id)
            .where(TaskGuard.task_id == task.id)
            .order_by(Guard.title.asc())
        )
    ).all()
    guards = [
        {
            "title": title,
            "type": guard_type,
            "command": command,
            "skippable": skippable,
            "status": status,
            "result": result,
        }
        for title, guard_type, command, skippable, status, result in guard_rows
    ]

    skill_rows = (
        await db.execute(
            select(Skill.id, Skill.title, Skill.lifecycle, TaskSkill.pinned_version_id)
            .join(TaskSkill, TaskSkill.skill_id == Skill.id)
            .where(TaskSkill.task_id == task.id)
            .order_by(Skill.title.asc())
        )
    ).all()
    linked_skills = [
        {
            "id": str(skill_id),
            "title": title,
            "lifecycle": lifecycle,
            "pinned_version_id": str(pinned_version_id) if pinned_version_id else None,
            "resource_uri": _skill_uri(title),
        }
        for skill_id, title, lifecycle, pinned_version_id in skill_rows
    ]

    boundary_row = await db.execute(select(ContextBoundary).where(ContextBoundary.task_id == task.id))
    cb = boundary_row.scalar_one_or_none()
    context_boundary = None
    if cb:
        context_boundary = {
            "resource_uri": _context_boundary_uri(task.task_key),
            "allowed_skills": [str(skill_id) for skill_id in (cb.allowed_skills or [])],
            "allowed_docs": [str(doc_id) for doc_id in (cb.allowed_docs or [])],
            "external_access": cb.external_access,
            "max_token_budget": cb.max_token_budget,
            "set_by": str(cb.set_by),
            "created_at": cb.created_at.isoformat(),
        }

    return json.dumps(
        {
            "task_key": task.task_key,
            "title": task.title,
            "description": task.description,
            "state": task.state,
            "definition_of_done": task.definition_of_done,
            "pinned_skills": task.pinned_skills,
            "linked_skills": linked_skills,
            "guards": guards,
            "context_boundary": context_boundary,
            "result": task.result,
            "artifacts": task.artifacts,
            "review_comment": task.review_comment,
        },
        default=str,
        ensure_ascii=False,
    )


async def _read_epic_resource(db: AsyncSession, epic_ref: str) -> str:
    epic = None
    try:
        epic_uuid = uuid.UUID(epic_ref)
        row = await db.execute(select(Epic).where(Epic.id == epic_uuid))
        epic = row.scalar_one_or_none()
    except ValueError:
        pass

    if epic is None:
        row = await db.execute(select(Epic).where(Epic.epic_key == epic_ref))
        epic = row.scalar_one_or_none()

    if not epic:
        return json.dumps({"error": f"Epic nicht gefunden: {epic_ref}"})

    task_rows = (
        await db.execute(
            select(Task.task_key, Task.title, Task.state)
            .where(Task.epic_id == epic.id)
            .order_by(Task.task_key.asc())
        )
    ).all()
    tasks = [{"task_key": key, "title": title, "state": state} for key, title, state in task_rows]

    dependency_keys = _infer_epic_dependencies(epic.epic_key)
    dependencies: list[dict[str, str | None]] = []
    if dependency_keys:
        dep_rows = (
            await db.execute(
                select(Epic.epic_key, Epic.title, Epic.state).where(Epic.epic_key.in_(dependency_keys))
            )
        ).all()
        dependencies = [
            {"epic_key": dep_key, "title": dep_title, "state": dep_state}
            for dep_key, dep_title, dep_state in dep_rows
        ]

    return json.dumps(
        {
            "epic_id": str(epic.id),
            "epic_key": epic.epic_key,
            "title": epic.title,
            "description": epic.description,
            "state": epic.state,
            "tasks": tasks,
            "dependencies": dependencies,
        },
        default=str,
        ensure_ascii=False,
    )


async def _read_wiki_resource(db: AsyncSession, slug: str) -> str:
    row = await db.execute(
        select(WikiArticle).where(WikiArticle.slug == slug, WikiArticle.deleted_at.is_(None))
    )
    article = row.scalar_one_or_none()
    if not article:
        return f"Wiki-Artikel nicht gefunden: {slug}"
    return article.content


async def _read_skill_resource(db: AsyncSession, skill_ref: str) -> str:
    exact_row = await db.execute(
        select(Skill).where(func.lower(Skill.title) == skill_ref.lower(), Skill.deleted_at.is_(None))
    )
    skill = exact_row.scalar_one_or_none()
    if skill:
        return skill.content

    normalized_ref = _slugify(skill_ref)
    skill_rows = (await db.execute(select(Skill).where(Skill.deleted_at.is_(None)))).scalars().all()
    slug_match = next((entry for entry in skill_rows if _slugify(entry.title) == normalized_ref), None)
    if not slug_match:
        return f"Skill nicht gefunden: {skill_ref}"
    return slug_match.content


async def _read_context_boundary_resource(db: AsyncSession, task_key: str) -> str:
    row = await db.execute(
        select(ContextBoundary, Task)
        .join(Task, ContextBoundary.task_id == Task.id)
        .where(Task.task_key == task_key)
        .limit(1)
    )
    result = row.one_or_none()
    if not result:
        return json.dumps({"error": f"Context Boundary nicht gefunden für: {task_key}"})

    cb, task = result
    return json.dumps(
        {
            "task_key": task.task_key,
            "task_state": task.state,
            "allowed_skills": [str(skill_id) for skill_id in (cb.allowed_skills or [])],
            "allowed_docs": [str(doc_id) for doc_id in (cb.allowed_docs or [])],
            "external_access": cb.external_access,
            "max_token_budget": cb.max_token_budget,
            "version": cb.version,
            "set_by": str(cb.set_by),
            "created_at": cb.created_at.isoformat(),
        },
        default=str,
        ensure_ascii=False,
    )


async def _read_prompt_resource(db: AsyncSession, role: str) -> str:
    valid_roles = {"worker", "reviewer", "review", "gaertner", "kartograph", "stratege", "architekt", "triage"}
    if role not in valid_roles:
        return f"Unbekannte Rolle: {role}. Gültig: {', '.join(sorted(valid_roles))}"

    prompt_type, generate_args, error_text = await _resolve_prompt_args(db, role)
    if error_text:
        return error_text

    generator = PromptGenerator(db)
    prompt = await generator.generate(prompt_type, **generate_args)
    await db.commit()
    return prompt


async def _read_health_report_resource(db: AsyncSession) -> str:
    report_task = await _find_latest_health_report(db)
    if not report_task:
        return "Kein Repo-Health-Report vorhanden."
    return (
        f"# Repo Health Report\n\n"
        f"- Source Task: {report_task.task_key}\n"
        f"- Updated At: {report_task.updated_at}\n\n"
        f"{report_task.result or ''}"
    )


@server.read_resource()
async def read_resource(uri: Any) -> str:
    """Read a single MCP resource by URI."""
    uri_str = str(uri)

    try:
        res_type, res_id = _parse_resource_uri(uri_str)
        async with AsyncSessionLocal() as db:
            if res_type == "task":
                payload = await _read_task_resource(db, res_id)
                await db.commit()
                return payload
            if res_type == "epic":
                return await _read_epic_resource(db, res_id)
            if res_type == "wiki":
                return await _read_wiki_resource(db, res_id)
            if res_type == "skill":
                return await _read_skill_resource(db, res_id)
            if res_type == "context-boundary":
                return await _read_context_boundary_resource(db, res_id)
            if res_type == "prompt":
                return await _read_prompt_resource(db, res_id)
            if res_type == "health-report":
                return await _read_health_report_resource(db)
            return json.dumps({"error": f"Unbekannter Resource-Typ: {res_type}"})
    except Exception as exc:
        logger.exception("read_resource failed for URI %s", uri_str)
        return json.dumps({"error": str(exc)})
