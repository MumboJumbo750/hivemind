import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.epic import Epic
from app.schemas.epic import EpicCreate, EpicUpdate
from app.services.embedding_service import get_embedding_service
from app.services.locking import check_version

logger = logging.getLogger(__name__)
EMBEDDING_SVC = get_embedding_service()


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
        entered_scoped = False
        if data.expected_version is not None:
            check_version(epic, data.expected_version)
        if data.title is not None:
            epic.title = data.title
        if data.description is not None:
            epic.description = data.description
        if data.state is not None:
            old_state = epic.state
            epic.state = data.state
            entered_scoped = old_state != "scoped" and data.state == "scoped"
            # Epic-Cancel: expire open decision_requests + stop SLA processing
            if data.state == "cancelled" and old_state != "cancelled":
                await self._expire_epic_decision_requests(epic.id)
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
        if entered_scoped:
            await self._compute_epic_embedding(epic)
        await self.db.refresh(epic)
        return epic

    async def _compute_epic_embedding(self, epic: Epic) -> None:
        """Compute and persist epic embedding when entering scoped state."""
        text_input = _build_epic_embedding_text(epic)
        try:
            embedding = await EMBEDDING_SVC.embed(text_input)
        except Exception as exc:
            logger.warning("Epic embedding failed for %s: %s", epic.epic_key, exc)
            return

        if not embedding:
            logger.info("Epic embedding unavailable for %s (feature degradation)", epic.epic_key)
            return

        await self.db.execute(
            text(
                "UPDATE epics "
                "SET embedding = :embedding::vector, embedding_model = :model "
                "WHERE id = :id"
            ),
            {
                "embedding": str(embedding),
                "model": settings.hivemind_embedding_model,
                "id": str(epic.id),
            },
        )
        epic.embedding_model = settings.hivemind_embedding_model

    async def _expire_epic_decision_requests(self, epic_id: uuid.UUID) -> int:
        """Expire all open decision_requests for a cancelled epic (TASK-6 acceptance criterion)."""
        from app.models.decision import DecisionRequest

        result = await self.db.execute(
            select(DecisionRequest).where(
                DecisionRequest.epic_id == epic_id,
                DecisionRequest.state == "open",
            )
        )
        count = 0
        now = datetime.now(timezone.utc)
        for dr in result.scalars().all():
            dr.state = "expired"
            dr.resolved_at = now
            dr.version += 1
            count += 1
        if count:
            await self.db.flush()
        return count


def _build_epic_embedding_text(epic: Epic) -> str:
    parts = [epic.title.strip()]
    if epic.description:
        parts.append(epic.description.strip())
    if epic.dod_framework:
        parts.append(json.dumps(epic.dod_framework, sort_keys=True, ensure_ascii=True))
    return "\n\n".join(p for p in parts if p).strip()
