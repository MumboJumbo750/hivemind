"""REST CRUD for Code Nodes — TASK-3-010.

Endpoints:
  POST   /api/code-nodes     — Create code node (kartograph + admin)
  PATCH  /api/code-nodes/{id} — Update code node (kartograph + admin)
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import CurrentActor, require_role
from app.schemas.crud import CodeNodeCreate, CodeNodeResponse, CodeNodeUpdate
from app.services import code_node_service
from app.services.audit import write_audit

router = APIRouter(prefix="/code-nodes", tags=["code-nodes"])


@router.post("/", response_model=CodeNodeResponse, status_code=status.HTTP_201_CREATED)
async def create_code_node(
    body: CodeNodeCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("kartograph", "admin")),
):
    """Create a new code node (kartograph + admin)."""
    node = await code_node_service.create_code_node(db, body, actor.id)

    await write_audit(
        tool_name="create_code_node",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(node.id),
    )
    return node  # type: ignore[return-value]


@router.patch("/{node_id}", response_model=CodeNodeResponse)
async def update_code_node(
    node_id: uuid.UUID,
    body: CodeNodeUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("kartograph", "admin")),
):
    """Update an existing code node (kartograph + admin)."""
    node = await code_node_service.update_code_node(db, node_id, body)

    await write_audit(
        tool_name="update_code_node",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(node.id),
    )
    return node  # type: ignore[return-value]
