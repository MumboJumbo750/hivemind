import json
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.doc import Doc
from app.models.federation import Node
from app.models.sync import SyncOutbox
from app.models.task import Task
from app.routers.deps import get_current_actor, require_role
from app.schemas.auth import CurrentActor
from app.schemas.crud import DocCreate, DocResponse
from app.schemas.epic import EpicCreate, EpicResponse, EpicShareRequest, EpicShareResponse, EpicUpdate
from app.schemas.task import TaskCreate, TaskResponse
from app.services.audit import write_audit
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
        node_result = await db.execute(select(Node).where(Node.id.in_(node_ids)))
        for n in node_result.scalars().all():
            node_map[n.id] = n.node_name

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
    epic = await svc.get_by_key(epic_key)  # raises 404
    doc = Doc(
        title=body.title,
        content=body.content,
        epic_id=epic.id,
        version=1,
        updated_by=actor.id,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="create_epic_doc",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(doc.id),
        epic_id=epic.id,
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
    # 1. Load & validate epic
    svc = EpicService(db)
    epic = await svc.get_by_key(epic_key)  # raises 404 internally
    if epic.state not in ("scoped", "active"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Epic state must be 'scoped' or 'active', got '{epic.state}'",
        )

    # 2. Load & validate peer node
    result = await db.execute(
        select(Node).where(Node.id == body.peer_node_id, Node.deleted_at.is_(None))
    )
    peer = result.scalar_one_or_none()
    if peer is None:
        raise HTTPException(status_code=404, detail="Peer node not found")
    if peer.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Peer node is not active (status='{peer.status}')",
        )

    # 3. Load tasks for the epic
    task_result = await db.execute(
        select(Task).where(Task.epic_id == epic.id)
    )
    all_tasks = list(task_result.scalars().all())

    # 4. Optionally assign tasks to peer
    if body.task_ids:
        task_ids_set = set(body.task_ids)
        for task in all_tasks:
            if task.id in task_ids_set:
                task.assigned_node_id = body.peer_node_id
        await db.flush()

    # 5. Serialize epic + tasks
    tasks_payload = []
    for t in all_tasks:
        tasks_payload.append({
            "external_id": t.external_id or t.task_key,
            "title": t.title,
            "description": t.description,
            "state": t.state,
            "definition_of_done": t.definition_of_done,
            "pinned_skills": t.pinned_skills or [],
            "assigned_node_id": str(t.assigned_node_id) if t.assigned_node_id else None,
        })

    payload = {
        "external_id": epic.external_id or epic.epic_key,
        "title": epic.title,
        "description": epic.description,
        "priority": epic.priority or "medium",
        "definition_of_done": epic.dod_framework,
        "tasks": tasks_payload,
    }

    # 6. Create outbox entry
    outbox_entry = SyncOutbox(
        dedup_key=f"epic_share:{epic.id}:{body.peer_node_id}",
        direction="peer_outbound",
        system="federation",
        target_node_id=body.peer_node_id,
        entity_type="epic_shared",
        entity_id=str(epic.id),
        payload=payload,
    )
    db.add(outbox_entry)
    await db.flush()
    await db.refresh(outbox_entry)
    await db.commit()

    return EpicShareResponse(
        outbox_id=outbox_entry.id,
        epic_key=epic.epic_key,
        peer_node_id=body.peer_node_id,
        task_count=len(all_tasks),
    )
