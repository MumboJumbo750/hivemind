"""REST CRUD for Guards — TASK-3-010.

Endpoints:
  POST   /api/guards     — Create guard (admin only)
  PATCH  /api/guards/{id} — Update guard (admin only)
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import CurrentActor, require_role
from app.schemas.crud import GuardCreate, GuardResponse, GuardUpdate
from app.services.audit import write_audit
from app.services.governance import create_guard as _svc_create_guard, update_guard_record

router = APIRouter(prefix="/guards", tags=["guards"])


@router.post("/", response_model=GuardResponse, status_code=status.HTTP_201_CREATED)
async def create_guard(
    body: GuardCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
):
    """Create a new guard (admin only)."""
    guard = await _svc_create_guard(db, body, actor)

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
    guard = await update_guard_record(db, guard_id, body, actor)

    await write_audit(
        tool_name="update_guard",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(guard.id),
    )
    return guard  # type: ignore[return-value]
