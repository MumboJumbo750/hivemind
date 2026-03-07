"""Spotlight-Search Backend (TASK-2-010).

GET /api/search?q=<query>&type=tasks,epics&limit=20
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.services import search_service

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
    return await search_service.get_accessible_project_ids(db, actor.id)


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
        if not is_solo_or_admin:
            project_ids = await _accessible_project_ids(db, actor)
            if not project_ids:
                results["epics"] = []
            else:
                epics = await search_service.search_epics(db, q, limit, project_ids)
                results["epics"] = [
                    SearchResult(
                        type="epic",
                        id=e.id,
                        title=e.title,
                        url=f"/command-deck?epic={e.epic_key}",
                    )
                    for e in epics
                ]
        else:
            epics = await search_service.search_epics(db, q, limit)
            results["epics"] = [
                SearchResult(
                    type="epic",
                    id=e.id,
                    title=e.title,
                    url=f"/command-deck?epic={e.epic_key}",
                )
                for e in epics
            ]

    if "tasks" in types:
        if not is_solo_or_admin:
            project_ids = await _accessible_project_ids(db, actor)
            if not project_ids:
                results["tasks"] = []
            else:
                task_rows = await search_service.search_tasks(db, q, limit, project_ids)
                results["tasks"] = [
                    SearchResult(
                        type="task",
                        id=t.id,
                        title=t.title,
                        subtitle=epic_title,
                        url=f"/command-deck?epic={epic_key}&task={t.task_key}",
                    )
                    for t, epic_title, epic_key in task_rows
                ]
        else:
            task_rows = await search_service.search_tasks(db, q, limit)
            results["tasks"] = [
                SearchResult(
                    type="task",
                    id=t.id,
                    title=t.title,
                    subtitle=epic_title,
                    url=f"/command-deck?epic={epic_key}&task={t.task_key}",
                )
                for t, epic_title, epic_key in task_rows
            ]

    return results
