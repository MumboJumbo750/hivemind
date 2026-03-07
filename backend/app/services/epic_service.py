import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.doc import Doc
from app.models.epic import Epic
from app.models.federation import Node
from app.models.sync import SyncOutbox
from app.models.task import Task
from app.schemas.epic import EpicCreate, EpicShareRequest, EpicUpdate
from app.services.embedding_service import EmbeddingPriority, get_embedding_service
from app.services.locking import check_version

logger = logging.getLogger(__name__)
EMBEDDING_SVC = get_embedding_service()


async def _next_epic_key(db: AsyncSession) -> str:
    from app.services.key_generator import next_epic_key
    return await next_epic_key(db)


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

    async def get_by_id_or_none(self, epic_id: uuid.UUID) -> Epic | None:
        """Gibt Epic per UUID zurück oder None (kein 404)."""
        result = await self.db.execute(select(Epic).where(Epic.id == epic_id))
        return result.scalar_one_or_none()

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
        await self._trigger_conductor_epic_created(epic)
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
        if entered_scoped:
            await self._trigger_conductor_epic_scoped(epic)
        return epic

    async def _compute_epic_embedding(self, epic: Epic) -> None:
        """Queue epic embedding refresh when entering scoped state."""
        text_input = _build_epic_embedding_text(epic)
        await EMBEDDING_SVC.enqueue(
            "epics",
            str(epic.id),
            text_input,
            priority=EmbeddingPriority.ON_WRITE,
        )

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

    async def _trigger_conductor_epic_created(self, epic: Epic) -> None:
        try:
            from app.services.conductor import conductor

            await conductor.on_epic_created(str(epic.id), self.db)
        except Exception:
            logger.exception("Conductor hook failed for epic create %s", epic.epic_key)

    async def _trigger_conductor_epic_scoped(self, epic: Epic) -> None:
        try:
            from app.services.conductor import conductor

            await conductor.on_epic_scoped(str(epic.id), self.db)
        except Exception:
            logger.exception("Conductor hook failed for epic scoped %s", epic.epic_key)


    # ─── Doc helpers ─────────────────────────────────────────────────────────

    async def resolve_node_names(self, node_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Resolve a set of Node UUIDs to their node_name."""
        result = await self.db.execute(select(Node).where(Node.id.in_(node_ids)))
        return {n.id: n.node_name for n in result.scalars().all()}

    async def create_doc(self, epic_key: str, title: str, content: str, updated_by: uuid.UUID) -> Doc:
        """Create a new doc attached to the given epic (raises 404 if epic not found)."""
        epic = await self.get_by_key(epic_key)
        doc = Doc(
            title=title,
            content=content,
            epic_id=epic.id,
            version=1,
            updated_by=updated_by,
        )
        self.db.add(doc)
        await self.db.flush()
        await self.db.refresh(doc)
        await EMBEDDING_SVC.enqueue(
            "docs",
            str(doc.id),
            _build_doc_embedding_text(doc),
            priority=EmbeddingPriority.ON_WRITE,
        )
        return doc

    async def share(self, epic_key: str, body: EpicShareRequest) -> tuple["SyncOutbox", int]:
        """Share an epic with its tasks to a peer node via outbox."""
        from fastapi import HTTPException
        epic = await self.get_by_key(epic_key)
        if epic.state not in ("scoped", "active"):
            raise HTTPException(
                status_code=400,
                detail=f"Epic state must be 'scoped' or 'active', got '{epic.state}'",
            )

        peer_result = await self.db.execute(
            select(Node).where(Node.id == body.peer_node_id, Node.deleted_at.is_(None))
        )
        peer = peer_result.scalar_one_or_none()
        if peer is None:
            raise HTTPException(status_code=404, detail="Peer node not found")
        if peer.status != "active":
            raise HTTPException(
                status_code=400,
                detail=f"Peer node is not active (status='{peer.status}')",
            )

        task_result = await self.db.execute(select(Task).where(Task.epic_id == epic.id))
        all_tasks = list(task_result.scalars().all())

        if body.task_ids:
            task_ids_set = set(body.task_ids)
            for task in all_tasks:
                if task.id in task_ids_set:
                    task.assigned_node_id = body.peer_node_id
            await self.db.flush()

        tasks_payload = [
            {
                "external_id": t.external_id or t.task_key,
                "title": t.title,
                "description": t.description,
                "state": t.state,
                "definition_of_done": t.definition_of_done,
                "pinned_skills": t.pinned_skills or [],
                "assigned_node_id": str(t.assigned_node_id) if t.assigned_node_id else None,
            }
            for t in all_tasks
        ]
        payload = {
            "external_id": epic.external_id or epic.epic_key,
            "title": epic.title,
            "description": epic.description,
            "priority": epic.priority or "medium",
            "definition_of_done": epic.dod_framework,
            "tasks": tasks_payload,
        }

        outbox_entry = SyncOutbox(
            dedup_key=f"epic_share:{epic.id}:{body.peer_node_id}",
            direction="peer_outbound",
            system="federation",
            target_node_id=body.peer_node_id,
            entity_type="epic_shared",
            entity_id=str(epic.id),
            payload=payload,
        )
        self.db.add(outbox_entry)
        await self.db.flush()
        await self.db.refresh(outbox_entry)
        return outbox_entry, len(all_tasks)


def _build_epic_embedding_text(epic: Epic) -> str:
    parts = [epic.title.strip()]
    if epic.description:
        parts.append(epic.description.strip())
    if epic.dod_framework:
        parts.append(json.dumps(epic.dod_framework, sort_keys=True, ensure_ascii=True))
    return "\n\n".join(p for p in parts if p).strip()


def _build_doc_embedding_text(doc: Doc) -> str:
    parts = [doc.title.strip(), doc.content.strip()]
    return "\n\n".join(part for part in parts if part).strip()
