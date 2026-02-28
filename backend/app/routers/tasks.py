import time

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.schemas.task import TaskResponse, TaskReview, TaskStateTransition, TaskUpdate
from app.services.audit import write_audit
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_key}", response_model=TaskResponse)
async def get_task(
    task_key: str,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    svc = TaskService(db)
    return await svc.get_by_key(task_key)  # type: ignore[return-value]


@router.patch("/{task_key}", response_model=TaskResponse)
async def update_task(
    task_key: str,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> TaskResponse:
    t0 = time.perf_counter()
    svc = TaskService(db)
    task = await svc.update(task_key, body)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="update_task",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"task_key": task.task_key, "version": task.version},
        epic_id=task.epic_id,
        target_id=task.task_key,
        idempotency_key=body.idempotency_key,
        duration_ms=duration,
    )
    return task  # type: ignore[return-value]


@router.patch("/{task_key}/state", response_model=TaskResponse)
async def transition_task_state(
    task_key: str,
    body: TaskStateTransition,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> TaskResponse:
    t0 = time.perf_counter()
    svc = TaskService(db)
    task = await svc.transition_state(task_key, body)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="transition_task_state",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"task_key": task.task_key, "state": task.state},
        epic_id=task.epic_id,
        target_id=task.task_key,
        duration_ms=duration,
    )
    return task  # type: ignore[return-value]


@router.post(
    "/{task_key}/review",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
)
async def review_task(
    task_key: str,
    body: TaskReview,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> TaskResponse:
    t0 = time.perf_counter()
    svc = TaskService(db)
    task = await svc.review(task_key, body)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="review_task",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"task_key": task.task_key, "state": task.state},
        epic_id=task.epic_id,
        target_id=task.task_key,
        duration_ms=duration,
    )
    return task  # type: ignore[return-value]
