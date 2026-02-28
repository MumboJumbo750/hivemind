import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic import Epic
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskReview, TaskStateTransition, TaskUpdate
from app.services.locking import check_version
from app.services.state_machine import (
    calculate_epic_state_after_task_transition,
    validate_qa_failed_count,
    validate_review_gate,
    validate_task_transition,
)


async def _next_task_key(db: AsyncSession) -> str:
    result = await db.execute(text("SELECT nextval('task_key_seq')"))
    seq_val = result.scalar_one()
    return f"TASK-{seq_val}"


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

    async def transition_state(self, task_key: str, body: TaskStateTransition) -> Task:
        """State-Transition mit vollständiger Validierung + Epic-Auto-Transition."""
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
        return task

    async def review(self, task_key: str, body: TaskReview) -> Task:
        """approve_review oder reject_review."""
        task = await self.get_by_key(task_key)

        if task.state != "in_review":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Review nur aus 'in_review' möglich (aktuell: '{task.state}').",
            )

        if body.action == "approve":
            new_state = "done"
        elif body.action == "reject":
            new_state = "qa_failed"
            task.qa_failed_count += 1
            if body.comment:
                task.review_comment = body.comment
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="action muss 'approve' oder 'reject' sein.",
            )

        task.state = new_state
        task.version += 1
        await self.db.flush()

        # Federation: notify peer if task is delegated
        if task.assigned_node_id:
            from app.services.federation_service import notify_peer_task_update
            await notify_peer_task_update(
                self.db, task.id, task.task_key, new_state, task.assigned_node_id,
                result_text=task.result,
            )

        # Epic Auto-Transition (atomar)
        epic = await _get_epic(self.db, task.epic_id)
        sibling_states = await _all_sibling_states(self.db, task.epic_id)
        new_epic_state = calculate_epic_state_after_task_transition(
            epic.state, new_state, sibling_states
        )
        if new_epic_state:
            epic.state = new_epic_state
            epic.version += 1
            await self.db.flush()

        await self.db.refresh(task)
        return task
