"""Service layer for Spotlight Search.

Enthält alle DB-Zugriffe für search.py (epics, tasks, accessible project IDs).
"""
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic import Epic
from app.models.project import ProjectMember
from app.models.task import Task


async def get_accessible_project_ids(
    db: AsyncSession,
    actor_id: uuid.UUID,
) -> list[uuid.UUID]:
    """Gibt Projekt-IDs zurück, auf die der User Zugriff hat."""
    result = await db.execute(
        select(ProjectMember.project_id).where(ProjectMember.user_id == actor_id)
    )
    return [row[0] for row in result.all()]


async def search_epics(
    db: AsyncSession,
    q: str,
    limit: int = 20,
    project_ids: Optional[list[uuid.UUID]] = None,
) -> list[Epic]:
    """Suche Epics nach Titel. Wenn project_ids angegeben, wird auf diese gefiltert."""
    stmt = select(Epic).where(Epic.title.ilike(f"%{q}%")).limit(limit)
    if project_ids is not None:
        stmt = stmt.where(Epic.project_id.in_(project_ids))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def search_tasks(
    db: AsyncSession,
    q: str,
    limit: int = 20,
    project_ids: Optional[list[uuid.UUID]] = None,
) -> list[tuple]:
    """Suche Tasks nach Titel inkl. Epic-Informationen.

    Gibt Liste von (Task, epic_title, epic_key) Tuples zurück.
    Wenn project_ids angegeben, wird auf diese gefiltert.
    """
    stmt = (
        select(Task, Epic.title.label("epic_title"), Epic.epic_key)
        .join(Epic, Task.epic_id == Epic.id)
        .where(Task.title.ilike(f"%{q}%"))
        .limit(limit)
    )
    if project_ids is not None:
        stmt = stmt.where(Epic.project_id.in_(project_ids))
    result = await db.execute(stmt)
    return result.all()
