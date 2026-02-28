"""Spotlight-Search Backend (TASK-2-010).

GET /api/search?q=<query>&type=tasks,epics&limit=20
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.epic import Epic
from app.models.project import ProjectMember
from app.models.task import Task
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    type: str  # "task" | "epic"
    id: uuid.UUID
    title: str
    subtitle: Optional[str] = None  # Epic-Titel bei Tasks
    url: str


async def _accessible_project_ids(db: AsyncSession, actor: CurrentActor) -> list[uuid.UUID]:
    """Gibt Projekt-IDs zurück auf die der Actor Zugriff hat (Admin = alle)."""
    if actor.role == "admin":
        return []  # leere Liste = kein Filter nötig (Admin sieht alles)
    result = await db.execute(
        select(ProjectMember.project_id).where(ProjectMember.user_id == actor.id)
    )
    return [row[0] for row in result.all()]


@router.get("", response_model=dict)
async def spotlight_search(
    q: str = Query(min_length=2),
    type: str = Query(default="tasks,epics"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> dict:
    types = {t.strip() for t in type.split(",")}
    is_solo_or_admin = actor.role in ("admin", "solo")

    results: dict[str, list[SearchResult]] = {}

    if "epics" in types:
        q_epics = select(Epic).where(Epic.title.ilike(f"%{q}%")).limit(limit)
        if not is_solo_or_admin:
            project_ids = await _accessible_project_ids(db, actor)
            if not project_ids:
                results["epics"] = []
            else:
                q_epics = q_epics.where(Epic.project_id.in_(project_ids))
                epic_result = await db.execute(q_epics)
                results["epics"] = [
                    SearchResult(
                        type="epic",
                        id=e.id,
                        title=e.title,
                        url=f"/command-deck?epic={e.epic_key}",
                    )
                    for e in epic_result.scalars().all()
                ]
        else:
            epic_result = await db.execute(q_epics)
            results["epics"] = [
                SearchResult(
                    type="epic",
                    id=e.id,
                    title=e.title,
                    url=f"/command-deck?epic={e.epic_key}",
                )
                for e in epic_result.scalars().all()
            ]

    if "tasks" in types:
        q_tasks = (
            select(Task, Epic.title.label("epic_title"), Epic.epic_key)
            .join(Epic, Task.epic_id == Epic.id)
            .where(Task.title.ilike(f"%{q}%"))
            .limit(limit)
        )
        if not is_solo_or_admin:
            project_ids = await _accessible_project_ids(db, actor)
            if not project_ids:
                results["tasks"] = []
            else:
                q_tasks = q_tasks.where(Epic.project_id.in_(project_ids))
                task_result = await db.execute(q_tasks)
                results["tasks"] = [
                    SearchResult(
                        type="task",
                        id=t.id,
                        title=t.title,
                        subtitle=epic_title,
                        url=f"/command-deck?epic={epic_key}&task={t.task_key}",
                    )
                    for t, epic_title, epic_key in task_result.all()
                ]
        else:
            task_result = await db.execute(q_tasks)
            results["tasks"] = [
                SearchResult(
                    type="task",
                    id=t.id,
                    title=t.title,
                    subtitle=epic_title,
                    url=f"/command-deck?epic={epic_key}&task={t.task_key}",
                )
                for t, epic_title, epic_key in task_result.all()
            ]

    return results
