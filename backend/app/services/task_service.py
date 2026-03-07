import logging
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic import Epic
from app.models.guard import TaskGuard
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskReview, TaskStateTransition, TaskUpdate
from app.services.locking import check_version
from app.services.state_machine import (
    calculate_epic_state_after_task_transition,
    validate_qa_failed_count,
    validate_review_gate,
    validate_task_transition,
)

logger = logging.getLogger(__name__)


async def _next_task_key(db: AsyncSession) -> str:
    from app.services.key_generator import next_task_key
    return await next_task_key(db)


async def _get_epic(db: AsyncSession, epic_id: uuid.UUID) -> Epic:
    result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = result.scalar_one_or_none()
    if epic is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Epic nicht gefunden.")
    return epic


async def _all_sibling_states(db: AsyncSession, epic_id: uuid.UUID) -> list[str]:
    result = await db.execute(select(Task.state).where(Task.epic_id == epic_id))
    return [row[0] for row in result.all()]


class TaskService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_epic_key(
        self,
        epic_key: str,
        state: str | None = None,
        assigned_node_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        epic_result = await self.db.execute(select(Epic).where(Epic.epic_key == epic_key))
        epic = epic_result.scalar_one_or_none()
        if epic is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Epic '{epic_key}' nicht gefunden.",
            )
        return await self.list_by_epic(epic.id, state=state, assigned_node_id=assigned_node_id, limit=limit, offset=offset)

    async def list_by_epic(
        self,
        epic_id: uuid.UUID,
        state: str | None = None,
        assigned_node_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        q = select(Task).where(Task.epic_id == epic_id)
        if state:
            q = q.where(Task.state == state)
        if assigned_node_id is not None:
            q = q.where(Task.assigned_node_id == assigned_node_id)
        q = q.order_by(Task.created_at.asc()).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def get_by_key(self, task_key: str) -> Task:
        result = await self.db.execute(select(Task).where(Task.task_key == task_key))
        task = result.scalar_one_or_none()
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task '{task_key}' nicht gefunden.",
            )
        return task

    async def create(self, epic_key: str, data: TaskCreate, created_by: uuid.UUID) -> Task:
        # Resolve epic_key → epic
        epic_result = await self.db.execute(
            select(Epic).where(Epic.epic_key == epic_key)
        )
        epic = epic_result.scalar_one_or_none()
        if epic is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Epic '{epic_key}' nicht gefunden.",
            )
        task_key = await _next_task_key(self.db)
        task = Task(
            task_key=task_key,
            epic_id=epic.id,
            title=data.title,
            description=data.description,
            assigned_to=data.assigned_to,
            definition_of_done=data.definition_of_done,
            parent_task_id=data.parent_task_id,
            state="scoped",  # Architekt-erstellte Tasks starten in 'scoped'
        )
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def update(self, task_key: str, data: TaskUpdate) -> Task:
        task = await self.get_by_key(task_key)
        if data.expected_version is not None:
            check_version(task, data.expected_version)
        if data.title is not None:
            task.title = data.title
        if data.description is not None:
            task.description = data.description
        if data.assigned_to is not None:
            task.assigned_to = data.assigned_to
        if data.definition_of_done is not None:
            task.definition_of_done = data.definition_of_done
        if data.result is not None:
            task.result = data.result
        task.version += 1
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def _transition_state(
        self,
        task_key: str,
        body: TaskStateTransition,
        *,
        skip_conductor: bool,
    ) -> Task:
        """Internal transition helper with optional conductor suppression."""
        task = await self.get_by_key(task_key)
        current_state = task.state
        requested_state = body.state

        # Review-Gate: done nur aus in_review
        validate_review_gate(current_state, requested_state)

        # Allowed transitions check
        validate_task_transition(current_state, requested_state)

        # qa_failed_count >= 3 → escalated statt in_progress
        effective_state = validate_qa_failed_count(current_state, requested_state, task.qa_failed_count)

        # Update qa_failed_count on in_review → qa_failed
        if current_state == "in_review" and effective_state == "qa_failed":
            task.qa_failed_count += 1
            if body.comment:
                task.review_comment = body.comment

        task.state = effective_state
        task.version += 1
        await self.db.flush()

        # ── TASK-6-003: Escalation notification on 3x qa_failed ──────
        if effective_state == "escalated" and current_state == "qa_failed":
            await self._notify_escalation(task)

        # Federation: notify peer if task is delegated
        if task.assigned_node_id:
            from app.services.federation_service import notify_peer_task_update
            await notify_peer_task_update(
                self.db, task.id, task.task_key, effective_state, task.assigned_node_id,
                result_text=task.result,
            )

        # Epic Auto-Transition (atomar in derselben Transaktion)
        epic = await _get_epic(self.db, task.epic_id)
        sibling_states = await _all_sibling_states(self.db, task.epic_id)
        new_epic_state = calculate_epic_state_after_task_transition(
            epic.state, effective_state, sibling_states
        )
        if new_epic_state:
            epic.state = new_epic_state
            epic.version += 1
            await self.db.flush()

        await self.db.refresh(task)
        if not skip_conductor:
            await self._trigger_conductor_task_state_change(task, current_state, effective_state)
        return task

    async def transition_state(
        self,
        task_key: str,
        body: TaskStateTransition,
        *,
        skip_conductor: bool = False,
    ) -> Task:
        """State-Transition mit vollständiger Validierung + optionalem Conductor-Hook."""
        return await self._transition_state(task_key, body, skip_conductor=skip_conductor)

    async def review(self, task_key: str, body: TaskReview) -> Task:
        """approve_review oder reject_review."""
        from app.services.review_workflow import approve_task_review, reject_task_review

        task = await self.get_by_key(task_key)

        if task.state != "in_review":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Review nur aus 'in_review' möglich (aktuell: '{task.state}').",
            )

        if body.action == "approve":
            await approve_task_review(
                self.db,
                task,
                comment=body.comment or "Review approved",
            )
        elif body.action == "reject":
            await reject_task_review(
                self.db,
                task,
                comment=body.comment or "Review rejected",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="action muss 'approve' oder 'reject' sein.",
            )

        # Federation: notify peer if task is delegated
        if task.assigned_node_id:
            from app.services.federation_service import notify_peer_task_update
            await notify_peer_task_update(
                self.db, task.id, task.task_key, task.state, task.assigned_node_id,
                result_text=task.result,
            )

        await self.db.refresh(task)
        return task

    async def reenter_from_qa_failed(
        self,
        task_key: str,
        *,
        skip_conductor: bool = False,
    ) -> Task:
        """qa_failed → in_progress: Guard-Reset + Eskalations-Check (TASK-5-005)."""
        return await self._reenter_from_qa_failed(task_key, skip_conductor=skip_conductor)

    async def _reenter_from_qa_failed(
        self,
        task_key: str,
        *,
        skip_conductor: bool,
    ) -> Task:
        """Internal qa_failed re-entry helper with optional conductor suppression."""
        task = await self.get_by_key(task_key)
        previous_state = task.state

        if task.state != "qa_failed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Task muss 'qa_failed' sein (aktuell: '{task.state}').",
            )

        # Escalation: 3x qa_failed → escalated statt in_progress
        if (task.qa_failed_count or 0) >= 3:
            task.state = "escalated"
            task.version += 1
            await self.db.flush()
            await self.db.refresh(task)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Task '{task_key}' wurde nach {task.qa_failed_count}x QA-Failure eskaliert. "
                    "Manueller Eingriff erforderlich."
                ),
            )

        # Normal re-entry: qa_failed → in_progress
        task.state = "in_progress"
        task.version += 1

        # Alle Guards auf pending zurücksetzen
        guard_result = await self.db.execute(
            select(TaskGuard).where(TaskGuard.task_id == task.id)
        )
        for tg in guard_result.scalars().all():
            if tg.status != "pending":
                tg.status = "pending"
                tg.output = None
                tg.source = None
                tg.checked_at = None

        await self.db.flush()
        await self.db.refresh(task)
        if not skip_conductor:
            await self._trigger_conductor_task_state_change(task, previous_state, task.state)
        return task

    async def get_context_boundary(self, task_key: str):
        """Resolve task_key → ContextBoundary (or None if unset)."""
        from app.models.context_boundary import ContextBoundary
        result = await self.db.execute(select(Task.id).where(Task.task_key == task_key))
        task_id = result.scalar_one_or_none()
        if task_id is None:
            raise HTTPException(status_code=404, detail=f"Task {task_key} not found")
        result2 = await self.db.execute(
            select(ContextBoundary).where(ContextBoundary.task_id == task_id)
        )
        return result2.scalar_one_or_none()

    async def _notify_escalation(self, task: Task) -> None:
        """Send escalation notification to epic owner + admins (TASK-6-003)."""
        try:
            from app.services.notification_service import (
                create_notification,
                get_admin_user_ids,
                notify_users,
            )
            from app.services.audit import write_audit

            epic = await _get_epic(self.db, task.epic_id)
            entity_id = str(task.id)
            body = (
                f"Task '{task.title}' ({task.task_key}) wurde nach 3x qa_failed "
                f"automatisch eskaliert."
            )

            # Notify epic owner
            if epic.owner_id:
                await create_notification(
                    self.db,
                    user_id=epic.owner_id,
                    notification_type="escalation",
                    body=body,
                    link=f"/tasks/{task.task_key}",
                    entity_type="task",
                    entity_id=entity_id,
                )

            # Notify all admins (deduplicate with owner)
            admin_ids = await get_admin_user_ids(self.db)
            owner_set = {epic.owner_id} if epic.owner_id else set()
            other_admins = [uid for uid in admin_ids if uid not in owner_set]
            if other_admins:
                await notify_users(
                    self.db,
                    user_ids=other_admins,
                    notification_type="escalation",
                    body=body,
                    link=f"/tasks/{task.task_key}",
                    entity_type="task",
                    entity_id=entity_id,
                )

            # Audit log
            await write_audit(
                tool_name="auto_escalation_3x_qa_failed",
                actor_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
                actor_role="system",
                input_payload={"task_key": task.task_key, "qa_failed_count": task.qa_failed_count},
                target_id=str(task.id),
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception("_notify_escalation failed (non-critical)")

    async def _trigger_conductor_task_state_change(
        self,
        task: Task,
        old_state: str,
        new_state: str,
    ) -> None:
        if old_state == new_state:
            return

        try:
            from app.services.conductor import conductor

            await conductor.on_task_state_change(
                task.task_key,
                str(task.id),
                old_state,
                new_state,
                self.db,
            )
        except Exception:
            logger.exception(
                "Conductor hook failed for task %s (%s -> %s)",
                task.task_key,
                old_state,
                new_state,
            )
