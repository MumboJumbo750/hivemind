"""Materialize active guards into task_guards for matching tasks."""
from __future__ import annotations

import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context_boundary import TaskSkill
from app.models.epic import Epic
from app.models.guard import Guard, TaskGuard
from app.models.skill import Skill
from app.models.task import Task


def _normalize_scope(values: list[str] | None) -> set[str]:
    return {
        value.strip().lower()
        for value in (values or [])
        if isinstance(value, str) and value.strip()
    }


def _guard_matches_scope(
    guard: Guard,
    *,
    task_scope: set[str],
    skill_scope: set[str],
) -> bool:
    guard_scope = _normalize_scope(guard.scope)
    if not guard_scope:
        return True
    return bool(guard_scope & task_scope) or bool(guard_scope & skill_scope)


async def _get_task_project_id(db: AsyncSession, task: Task) -> uuid.UUID | None:
    result = await db.execute(
        select(Epic.project_id).where(Epic.id == task.epic_id).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_task_relevant_skills(db: AsyncSession, task: Task) -> list[Skill]:
    linked_result = await db.execute(
        select(Skill)
        .join(TaskSkill, TaskSkill.skill_id == Skill.id)
        .where(TaskSkill.task_id == task.id, Skill.deleted_at.is_(None))
        .order_by(Skill.title.asc())
    )
    skills = list(linked_result.scalars().all())
    skill_ids = {skill.id for skill in skills}

    pinned_refs = [
        str(skill_ref).strip()
        for skill_ref in (task.pinned_skills or [])
        if str(skill_ref).strip()
    ]
    if not pinned_refs:
        return skills

    pinned_result = await db.execute(
        select(Skill)
        .where(Skill.source_slug.in_(pinned_refs), Skill.deleted_at.is_(None))
        .order_by(Skill.title.asc())
    )
    for skill in pinned_result.scalars().all():
        if skill.id not in skill_ids:
            skills.append(skill)
            skill_ids.add(skill.id)
    return skills


async def materialize_task_guards(db: AsyncSession, task: Task) -> int:
    """Create missing task_guards for all active guards matching this task."""
    existing_result = await db.execute(
        select(TaskGuard.guard_id).where(TaskGuard.task_id == task.id)
    )
    existing_guard_ids = set(existing_result.scalars().all())

    project_id = await _get_task_project_id(db, task)
    relevant_skills = await _get_task_relevant_skills(db, task)
    relevant_skill_ids = [skill.id for skill in relevant_skills]
    task_scope = {
        scope
        for skill in relevant_skills
        for scope in _normalize_scope(skill.service_scope)
    }
    skill_scopes = {
        skill.id: _normalize_scope(skill.service_scope)
        for skill in relevant_skills
    }

    skill_filter = Guard.skill_id.is_(None)
    if relevant_skill_ids:
        skill_filter = or_(Guard.skill_id.is_(None), Guard.skill_id.in_(relevant_skill_ids))

    project_filter = Guard.project_id.is_(None)
    if project_id:
        project_filter = or_(Guard.project_id.is_(None), Guard.project_id == project_id)

    guard_result = await db.execute(
        select(Guard)
        .where(
            Guard.lifecycle == "active",
            project_filter,
            skill_filter,
        )
        .order_by(Guard.created_at.asc())
    )
    guards = list(guard_result.scalars().all())

    created = 0
    for guard in guards:
        if guard.id in existing_guard_ids:
            continue
        if not _guard_matches_scope(
            guard,
            task_scope=task_scope,
            skill_scope=skill_scopes.get(guard.skill_id, set()),
        ):
            continue
        db.add(TaskGuard(task_id=task.id, guard_id=guard.id, status="pending"))
        existing_guard_ids.add(guard.id)
        created += 1

    if created:
        await db.flush()
    return created


async def materialize_guard_for_existing_tasks(db: AsyncSession, guard: Guard) -> int:
    """Apply one active guard to all currently matching tasks."""
    if guard.lifecycle != "active":
        return 0

    stmt = select(Task).join(Epic, Task.epic_id == Epic.id)
    if guard.project_id:
        stmt = stmt.where(Epic.project_id == guard.project_id)
    if guard.skill_id:
        stmt = (
            stmt.join(TaskSkill, TaskSkill.task_id == Task.id)
            .where(TaskSkill.skill_id == guard.skill_id)
            .distinct()
        )

    result = await db.execute(stmt.order_by(Task.created_at.asc()))
    created = 0
    for task in result.scalars().all():
        created += await materialize_task_guards(db, task)
    return created
