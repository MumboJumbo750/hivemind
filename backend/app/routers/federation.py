"""Federation Protocol API Router — TASK-F-004.

Endpoints:
  GET  /federation/ping            — public handshake
  POST /federation/skill/publish   — receive federated skill
  POST /federation/wiki/publish    — receive federated wiki article
  POST /federation/epic/share      — receive shared epic + tasks
  POST /federation/task/update     — receive task state update from peer
  POST /federation/sync            — bulk sync dispatcher
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.epic import Epic
from app.models.federation import Node, NodeIdentity
from app.models.skill import Skill
from app.models.task import Task
from app.models.wiki import WikiArticle
from app.schemas.federation import (
    FederatedEpicResponse,
    FederatedEpicShare,
    FederatedSkillPublish,
    FederatedSkillResponse,
    FederatedSyncItem,
    FederatedSyncRequest,
    FederatedSyncResponse,
    FederatedTaskUpdate,
    FederatedTaskUpdateResponse,
    FederatedWikiPublish,
    FederatedWikiResponse,
    PingResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/federation", tags=["federation"])


# ─── Ping ──────────────────────────────────────────────────────────────────────


@router.get("/ping", response_model=PingResponse)
async def ping(db: AsyncSession = Depends(get_db)) -> PingResponse:
    """Public liveness / handshake endpoint. Returns this node's identity."""
    result = await db.execute(select(NodeIdentity))
    identity = result.scalar_one_or_none()
    if identity is None:
        return PingResponse(
            node_id=uuid.UUID(int=0),
            node_name="uninitialized",
            public_key="",
        )
    return PingResponse(
        node_id=identity.node_id,
        node_name=identity.node_name,
        public_key=identity.public_key,
    )


# ─── Skill Publish ────────────────────────────────────────────────────────────


@router.post(
    "/skill/publish",
    response_model=FederatedSkillResponse,
    status_code=status.HTTP_200_OK,
)
async def skill_publish(
    body: FederatedSkillPublish,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FederatedSkillResponse:
    """Receive a federated skill from a peer. Upsert via origin_node_id + external_id."""
    origin_node_id = getattr(request.state, "federation_node_id", None)

    # Try to find existing by origin_node_id + title (or external_id)
    existing = None
    if body.external_id and origin_node_id:
        result = await db.execute(
            select(Skill).where(
                Skill.origin_node_id == origin_node_id,
                Skill.title == body.title,  # fallback match
            )
        )
        existing = result.scalar_one_or_none()

    if not existing and origin_node_id:
        # Also try by title match for same origin
        result = await db.execute(
            select(Skill).where(
                Skill.origin_node_id == origin_node_id,
                Skill.title == body.title,
            )
        )
        existing = result.scalar_one_or_none()

    if existing:
        # Update
        existing.content = body.content
        existing.service_scope = body.service_scope
        existing.stack = body.stack
        existing.lifecycle = body.lifecycle
        existing.version = body.version
        await db.flush()
        await db.refresh(existing)
        return FederatedSkillResponse(
            id=existing.id,
            title=existing.title,
            origin_node_id=existing.origin_node_id,
            federation_scope=existing.federation_scope,
            created=False,
        )

    # Create new federated skill
    skill = Skill(
        title=body.title,
        content=body.content,
        service_scope=body.service_scope,
        stack=body.stack,
        skill_type=body.skill_type,
        lifecycle=body.lifecycle,
        version=body.version,
        origin_node_id=origin_node_id,
        federation_scope="federated",
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)

    # SSE notification (TASK-F-015)
    from app.services.event_bus import publish as sse_publish
    # Resolve origin node name
    origin_name = None
    if origin_node_id:
        node_r = await db.execute(select(Node).where(Node.id == origin_node_id))
        node_obj = node_r.scalar_one_or_none()
        origin_name = node_obj.node_name if node_obj else None
    sse_publish("federation_skill", {
        "skill_id": str(skill.id),
        "title": skill.title,
        "origin_node_name": origin_name,
    })

    return FederatedSkillResponse(
        id=skill.id,
        title=skill.title,
        origin_node_id=skill.origin_node_id,
        federation_scope=skill.federation_scope,
        created=True,
    )


# ─── Wiki Publish ─────────────────────────────────────────────────────────────


@router.post(
    "/wiki/publish",
    response_model=FederatedWikiResponse,
    status_code=status.HTTP_200_OK,
)
async def wiki_publish(
    body: FederatedWikiPublish,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FederatedWikiResponse:
    """Receive a federated wiki article from a peer. Upsert via origin_node_id + slug."""
    origin_node_id = getattr(request.state, "federation_node_id", None)

    existing = None
    if origin_node_id:
        result = await db.execute(
            select(WikiArticle).where(
                WikiArticle.origin_node_id == origin_node_id,
                WikiArticle.slug == body.slug,
            )
        )
        existing = result.scalar_one_or_none()

    if existing:
        existing.title = body.title
        existing.content = body.content
        existing.tags = body.tags
        existing.version = body.version
        await db.flush()
        await db.refresh(existing)
        return FederatedWikiResponse(
            id=existing.id,
            title=existing.title,
            origin_node_id=existing.origin_node_id,
            federation_scope=existing.federation_scope,
            created=False,
        )

    article = WikiArticle(
        title=body.title,
        slug=body.slug,
        content=body.content,
        tags=body.tags,
        version=body.version,
        origin_node_id=origin_node_id,
        federation_scope="federated",
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)

    return FederatedWikiResponse(
        id=article.id,
        title=article.title,
        origin_node_id=article.origin_node_id,
        federation_scope=article.federation_scope,
        created=True,
    )


# ─── Epic Share ────────────────────────────────────────────────────────────────


async def _next_epic_key(db: AsyncSession) -> str:
    result = await db.execute(text("SELECT nextval('epic_key_seq')"))
    seq_val = result.scalar_one()
    return f"EPIC-FED-{seq_val}"


async def _next_task_key(db: AsyncSession) -> str:
    result = await db.execute(text("SELECT nextval('task_key_seq')"))
    seq_val = result.scalar_one()
    return f"TASK-{seq_val}"


@router.post(
    "/epic/share",
    response_model=FederatedEpicResponse,
    status_code=status.HTTP_201_CREATED,
)
async def epic_share(
    body: FederatedEpicShare,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FederatedEpicResponse:
    """Receive a shared epic + tasks from a peer. Create local mirror."""
    origin_node_id = getattr(request.state, "federation_node_id", None)

    epic_key = await _next_epic_key(db)
    epic = Epic(
        epic_key=epic_key,
        external_id=body.external_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        dod_framework=body.definition_of_done,
        origin_node_id=origin_node_id,
        state="scoped",
    )
    db.add(epic)
    await db.flush()

    # Create tasks
    task_count = 0
    for task_spec in body.tasks:
        task_key = await _next_task_key(db)
        task = Task(
            task_key=task_key,
            epic_id=epic.id,
            external_id=task_spec.external_id,
            title=task_spec.title,
            description=task_spec.description,
            state=task_spec.state or "incoming",
            definition_of_done=task_spec.definition_of_done,
            pinned_skills=task_spec.pinned_skills,
            assigned_node_id=task_spec.assigned_node_id,
        )
        db.add(task)
        task_count += 1

    await db.flush()
    await db.refresh(epic)

    return FederatedEpicResponse(
        id=epic.id,
        epic_key=epic.epic_key,
        title=epic.title,
        origin_node_id=epic.origin_node_id,
        task_count=task_count,
    )


# ─── Task Update ──────────────────────────────────────────────────────────────


@router.post(
    "/task/update",
    response_model=FederatedTaskUpdateResponse,
    status_code=status.HTTP_200_OK,
)
async def task_update(
    body: FederatedTaskUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FederatedTaskUpdateResponse:
    """Receive task state update from peer. Find task by external_id + origin context."""
    origin_node_id = getattr(request.state, "federation_node_id", None)

    # Find the task by external_id
    result = await db.execute(
        select(Task).where(Task.external_id == body.external_id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        # Also try by task_key
        result = await db.execute(
            select(Task).where(Task.task_key == body.external_id)
        )
        task = result.scalar_one_or_none()

    if task is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Task '{body.external_id}' not found")

    # Verify authority: only the assigned node can update
    if task.assigned_node_id and origin_node_id:
        if task.assigned_node_id != origin_node_id:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=403,
                detail="Only the assigned node can update this task",
            )

    # Validate state transition via state machine
    from app.services.state_machine import TASK_ALLOWED_TRANSITIONS
    if body.state not in TASK_ALLOWED_TRANSITIONS.get(task.state, set()):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"Invalid transition: {task.state} → {body.state}",
        )

    task.state = body.state
    if body.result:
        task.result = body.result
    task.version += 1
    await db.flush()
    await db.refresh(task)

    # SSE notification (TASK-F-015) — task_assigned event
    from app.services.event_bus import publish as sse_publish
    assigned_node_name = None
    if task.assigned_node_id:
        node_r = await db.execute(select(Node).where(Node.id == task.assigned_node_id))
        node_obj = node_r.scalar_one_or_none()
        assigned_node_name = node_obj.node_name if node_obj else None
    sse_publish("task_assigned", {
        "task_id": str(task.id),
        "task_title": task.title,
        "assigned_node_name": assigned_node_name,
    })

    return FederatedTaskUpdateResponse(
        task_key=task.task_key,
        state=task.state,
        updated=True,
    )


# ─── Sync (Bulk) ──────────────────────────────────────────────────────────────


@router.post(
    "/sync",
    response_model=FederatedSyncResponse,
    status_code=status.HTTP_200_OK,
)
async def sync(
    body: FederatedSyncRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FederatedSyncResponse:
    """Bulk sync: dispatch array of federated resources to individual handlers."""
    processed = 0
    errors = 0
    details: list[str] = []

    for item in body.items:
        try:
            if item.type == "skill":
                skill_data = FederatedSkillPublish(**item.payload)
                await skill_publish(skill_data, request, db)
                processed += 1
            elif item.type == "wiki":
                wiki_data = FederatedWikiPublish(**item.payload)
                await wiki_publish(wiki_data, request, db)
                processed += 1
            elif item.type == "epic":
                epic_data = FederatedEpicShare(**item.payload)
                await epic_share(epic_data, request, db)
                processed += 1
            elif item.type == "task_update":
                task_data = FederatedTaskUpdate(**item.payload)
                await task_update(task_data, request, db)
                processed += 1
            else:
                errors += 1
                details.append(f"Unknown type: {item.type}")
        except Exception as exc:
            errors += 1
            details.append(f"Error processing {item.type}: {str(exc)}")

    return FederatedSyncResponse(
        processed=processed,
        errors=errors,
        details=details,
    )
