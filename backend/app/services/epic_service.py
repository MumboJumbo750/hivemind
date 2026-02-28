import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic import Epic
from app.schemas.epic import EpicCreate, EpicUpdate
from app.services.locking import check_version


async def _next_epic_key(db: AsyncSession) -> str:
    result = await db.execute(text("SELECT nextval('epic_key_seq')"))
    seq_val = result.scalar_one()
    return f"EPIC-{seq_val}"


class EpicService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_project(
        self,
        project_id: uuid.UUID,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Epic]:
        q = select(Epic).where(Epic.project_id == project_id)
        if state:
            q = q.where(Epic.state == state)
        q = q.order_by(Epic.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_by_key(self, epic_key: str) -> Epic:
        result = await self.db.execute(select(Epic).where(Epic.epic_key == epic_key))
        epic = result.scalar_one_or_none()
        if epic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Epic '{epic_key}' nicht gefunden.")
        return epic

    async def create(self, project_id: uuid.UUID, data: EpicCreate, created_by: uuid.UUID) -> Epic:
        epic_key = await _next_epic_key(self.db)
        epic = Epic(
            epic_key=epic_key,
            project_id=project_id,
            title=data.title,
            description=data.description,
            owner_id=data.owner_id or created_by,
            priority=data.priority,
            sla_due_at=data.sla_due_at,
            dod_framework=data.dod_framework,
            state="incoming",
        )
        self.db.add(epic)
        await self.db.flush()
        await self.db.refresh(epic)
        return epic

    async def update(self, epic_key: str, data: EpicUpdate) -> Epic:
        epic = await self.get_by_key(epic_key)
        if data.expected_version is not None:
            check_version(epic, data.expected_version)
        if data.title is not None:
            epic.title = data.title
        if data.description is not None:
            epic.description = data.description
        if data.state is not None:
            epic.state = data.state
        if data.owner_id is not None:
            epic.owner_id = data.owner_id
        if data.backup_owner_id is not None:
            epic.backup_owner_id = data.backup_owner_id
        if data.priority is not None:
            epic.priority = data.priority
        if data.sla_due_at is not None:
            epic.sla_due_at = data.sla_due_at
        if data.dod_framework is not None:
            epic.dod_framework = data.dod_framework
        epic.version += 1
        await self.db.flush()
        await self.db.refresh(epic)
        return epic
