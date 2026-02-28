"""REST CRUD for Guards — TASK-3-010.

Endpoints:
  POST   /api/guards     — Create guard (admin only)
  PATCH  /api/guards/{id} — Update guard (admin only)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.guard import Guard
from app.routers.deps import CurrentActor, require_role
from app.schemas.crud import GuardCreate, GuardResponse, GuardUpdate
from app.services.audit import write_audit

router = APIRouter(prefix="/guards", tags=["guards"])


@router.post("/", response_model=GuardResponse, status_code=status.HTTP_201_CREATED)
async def create_guard(
    body: GuardCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """Create a new guard (admin only)."""
    guard = Guard(
        title=body.title,
        description=body.description,
        type=body.type,
        command=body.command,
        condition=body.condition,
        scope=body.scope,
        project_id=body.project_id,
        skill_id=body.skill_id,
        skippable=body.skippable,
        created_by=actor.id,
    )
    db.add(guard)
    await db.flush()
    await db.refresh(guard)

    await write_audit(
        tool_name="create_guard",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(guard.id),
    )
    return guard  # type: ignore[return-value]


@router.patch("/{guard_id}", response_model=GuardResponse)
async def update_guard(
    guard_id: uuid.UUID,
    body: GuardUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """Update an existing guard with optimistic locking (admin only)."""
    result = await db.execute(select(Guard).where(Guard.id == guard_id))
    guard = result.scalar_one_or_none()
    if not guard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guard nicht gefunden")

    if body.expected_version is not None and guard.version != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version-Conflict: erwartet {body.expected_version}, aktuell {guard.version}",
        )

    if body.title is not None:
        guard.title = body.title
    if body.description is not None:
        guard.description = body.description
    if body.type is not None:
        guard.type = body.type
    if body.command is not None:
        guard.command = body.command
    if body.condition is not None:
        guard.condition = body.condition
    if body.scope is not None:
        guard.scope = body.scope
    if body.skippable is not None:
        guard.skippable = body.skippable
    if body.lifecycle is not None:
        guard.lifecycle = body.lifecycle

    guard.version += 1
    await db.flush()
    await db.refresh(guard)

    await write_audit(
        tool_name="update_guard",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(guard.id),
    )
    return guard  # type: ignore[return-value]
