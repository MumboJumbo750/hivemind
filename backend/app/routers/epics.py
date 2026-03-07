import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor, require_role
from app.schemas.auth import CurrentActor
from app.schemas.crud import DocCreate, DocResponse
from app.schemas.epic import (
    EpicCreate,
    EpicRunResponse,
    EpicRunArtifactResponse,
    EpicResponse,
    EpicShareRequest,
    EpicShareResponse,
    EpicStartRequest,
    EpicStartResponse,
    EpicUpdate,
)
from app.schemas.task import TaskCreate, TaskResponse
from app.services.audit import write_audit
from app.services.epic_run_context import EpicRunContextService
from app.services.epic_run_service import EpicRunService
from app.services.epic_service import EpicService
from app.services.task_service import TaskService

router = APIRouter(tags=["epics"])


# ─── Epics under projects ─────────────────────────────────────────────────────

@router.get("/projects/{project_id}/epics", response_model=list[EpicResponse])
async def list_epics(
    project_id: uuid.UUID,
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[EpicResponse]:
    svc = EpicService(db)
    return await svc.list_by_project(project_id, state=state, limit=limit, offset=offset)  # type: ignore[return-value]


@router.post(
    "/projects/{project_id}/epics",
    response_model=EpicResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_epic(
    project_id: uuid.UUID,
    body: EpicCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicResponse:
    t0 = time.perf_counter()
    svc = EpicService(db)
    epic = await svc.create(project_id, body, created_by=actor.id)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="create_epic",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"epic_key": epic.epic_key},
        epic_id=epic.id,
        duration_ms=duration,
    )
    return epic  # type: ignore[return-value]


# ─── Epic detail by epic_key ─────────────────────────────────────────────────

@router.get("/epics/{epic_key}", response_model=EpicResponse)
async def get_epic(
    epic_key: str,
    db: AsyncSession = Depends(get_db),
) -> EpicResponse:
    svc = EpicService(db)
    return await svc.get_by_key(epic_key)  # type: ignore[return-value]


@router.patch("/epics/{epic_key}", response_model=EpicResponse)
async def update_epic(
    epic_key: str,
    body: EpicUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicResponse:
    t0 = time.perf_counter()
    svc = EpicService(db)
    epic = await svc.update(epic_key, body)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="update_epic",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"epic_key": epic.epic_key, "version": epic.version},
        epic_id=epic.id,
        idempotency_key=body.idempotency_key,
        duration_ms=duration,
    )
    return epic  # type: ignore[return-value]


@router.post("/epics/{epic_key}/start", response_model=EpicStartResponse)
async def start_epic(
    epic_key: str,
    body: EpicStartRequest,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicStartResponse:
    t0 = time.perf_counter()
    svc = EpicRunService(db)
    result = await svc.start(epic_key, body, actor)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="start_epic",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={
            "run_id": str(result.run_id),
            "status": result.status,
            "startable": result.startable,
            "blockers": [blocker.model_dump() for blocker in result.blockers],
        },
        target_id=epic_key,
        duration_ms=duration,
    )
    return result


@router.get("/epics/{epic_key}/runs", response_model=list[EpicRunResponse])
async def list_epic_runs(
    epic_key: str,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> list[EpicRunResponse]:
    svc = EpicRunService(db)
    runs = await svc.list_runs(epic_key, actor, limit=limit)
    return [EpicRunResponse.model_validate(run) for run in runs]


@router.get("/epic-runs/{run_id}", response_model=EpicRunResponse)
async def get_epic_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicRunResponse:
    svc = EpicRunService(db)
    run = await svc.get_run(run_id, actor)
    return EpicRunResponse.model_validate(run)


@router.get("/epic-runs/{run_id}/artifacts", response_model=list[EpicRunArtifactResponse])
async def list_epic_run_artifacts(
    run_id: uuid.UUID,
    artifact_type: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    task_key: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> list[EpicRunArtifactResponse]:
    svc = EpicRunContextService(db)
    await svc.verify_run_access(run_id, actor)
    artifacts = await svc.list_artifacts(
        run_id,
        artifact_type=artifact_type,
        state=state,
        task_key=task_key,
    )
    return [EpicRunArtifactResponse.model_validate(item) for item in artifacts]


# ─── Tasks under epics ───────────────────────────────────────────────────────

@router.get("/epics/{epic_key}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    epic_key: str,
    state: Optional[str] = Query(None),
    assigned_node_id: Optional[uuid.UUID] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[TaskResponse]:
    svc = TaskService(db)
    tasks = await svc.list_by_epic_key(
        epic_key, state=state, assigned_node_id=assigned_node_id, limit=limit, offset=offset,
    )

    # Resolve assigned_node_name for tasks with assigned_node_id
    node_ids = {t.assigned_node_id for t in tasks if t.assigned_node_id}
    node_map: dict[uuid.UUID, str] = {}
    if node_ids:
        svc_epic = EpicService(db)
        node_map = await svc_epic.resolve_node_names(node_ids)

    return [
        TaskResponse(
            id=t.id,
            task_key=t.task_key,
            epic_id=t.epic_id,
            parent_task_id=t.parent_task_id,
            title=t.title,
            description=t.description,
            state=t.state,
            version=t.version,
            definition_of_done=t.definition_of_done,
            assigned_to=t.assigned_to,
            assigned_node_id=t.assigned_node_id,
            assigned_node_name=node_map.get(t.assigned_node_id) if t.assigned_node_id else None,
            pinned_skills=t.pinned_skills,
            result=t.result,
            artifacts=t.artifacts,
            qa_failed_count=t.qa_failed_count,
            review_comment=t.review_comment,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in tasks
    ]


@router.post(
    "/epics/{epic_key}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    epic_key: str,
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> TaskResponse:
    t0 = time.perf_counter()
    svc = TaskService(db)
    task = await svc.create(epic_key, body, created_by=actor.id)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="create_task",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"task_key": task.task_key},
        epic_id=task.epic_id,
        target_id=task.task_key,
        duration_ms=duration,
    )
    return task  # type: ignore[return-value]


# ─── Epic Docs ────────────────────────────────────────────────────────────────

@router.post(
    "/epics/{epic_key}/docs",
    response_model=DocResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_epic_doc(
    epic_key: str,
    body: DocCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> DocResponse:
    """Create a new doc attached to an epic (admin only)."""
    t0 = time.perf_counter()
    svc = EpicService(db)
    doc = await svc.create_doc(epic_key, body.title, body.content, actor.id)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="create_epic_doc",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(doc.id),
        epic_id=doc.epic_id,
        duration_ms=duration,
    )
    return doc  # type: ignore[return-value]


# ─── Epic Share (Federation) ─────────────────────────────────────────────────

@router.post(
    "/epics/{epic_key}/share",
    response_model=EpicShareResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def share_epic(
    epic_key: str,
    body: EpicShareRequest,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicShareResponse:
    """Share an epic (with its tasks) to a peer node via outbox."""
    svc = EpicService(db)
    outbox_entry, task_count = await svc.share(epic_key, body)
    await db.commit()

    return EpicShareResponse(
        outbox_id=outbox_entry.id,
        epic_key=epic_key,
        peer_node_id=body.peer_node_id,
        task_count=task_count,
    )
