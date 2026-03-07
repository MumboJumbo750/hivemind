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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
import app.services.federation_service as fed_svc
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
    identity = await fed_svc.get_own_identity(db)
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

    skill, created = await fed_svc.upsert_federated_skill(db, origin_node_id, body)

    if created:
        # SSE notification (TASK-F-015)
        from app.services.event_bus import publish as sse_publish
        node_obj = await fed_svc.get_node_by_id(db, origin_node_id) if origin_node_id else None
        sse_publish("federation_skill", {
            "skill_id": str(skill.id),
            "title": skill.title,
            "origin_node_name": node_obj.node_name if node_obj else None,
        })

    return FederatedSkillResponse(
        id=skill.id,
        title=skill.title,
        origin_node_id=skill.origin_node_id,
        federation_scope=skill.federation_scope,
        created=created,
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

    article, created = await fed_svc.upsert_federated_wiki(db, origin_node_id, body)

    return FederatedWikiResponse(
        id=article.id,
        title=article.title,
        origin_node_id=article.origin_node_id,
        federation_scope=article.federation_scope,
        created=created,
    )


# ─── Epic Share ────────────────────────────────────────────────────────────────


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

    epic, task_count = await fed_svc.create_federated_epic(db, origin_node_id, body)

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

    try:
        task = await fed_svc.find_and_update_federated_task(db, origin_node_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # SSE notification (TASK-F-015) — task_assigned event
    from app.services.event_bus import publish as sse_publish
    node_obj = await fed_svc.get_node_by_id(db, task.assigned_node_id) if task.assigned_node_id else None
    sse_publish("task_assigned", {
        "task_id": str(task.id),
        "task_title": task.title,
        "assigned_node_name": node_obj.node_name if node_obj else None,
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
