"""REST CRUD for Code Nodes — TASK-3-010.

Endpoints:
  POST   /api/code-nodes     — Create code node (kartograph + admin)
  PATCH  /api/code-nodes/{id} — Update code node (kartograph + admin)
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.code_node import CodeNode
from app.routers.deps import CurrentActor, require_role
from app.schemas.crud import CodeNodeCreate, CodeNodeResponse, CodeNodeUpdate
from app.services.audit import write_audit

router = APIRouter(prefix="/code-nodes", tags=["code-nodes"])


@router.post("/", response_model=CodeNodeResponse, status_code=status.HTTP_201_CREATED)
async def create_code_node(
    body: CodeNodeCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("kartograph", "admin")),
):
    """Create a new code node (kartograph + admin)."""
    node = CodeNode(
        path=body.path,
        node_type=body.node_type,
        label=body.label,
        project_id=body.project_id,
        metadata_=body.metadata,
        explored_by=actor.id,
    )
    db.add(node)
    await db.flush()
    await db.refresh(node)

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
    result = await db.execute(select(CodeNode).where(CodeNode.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code-Node nicht gefunden")

    if body.label is not None:
        node.label = body.label
    if body.node_type is not None:
        node.node_type = body.node_type
    if body.metadata is not None:
        node.metadata_ = body.metadata

    await db.flush()
    await db.refresh(node)

    await write_audit(
        tool_name="update_code_node",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(node.id),
    )
    return node  # type: ignore[return-value]
