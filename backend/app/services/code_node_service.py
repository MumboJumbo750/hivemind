"""Service layer for Code Node CRUD operations.

Enthält alle DB-Zugriffe für code_nodes.py (create, get, update).
"""
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.code_node import CodeNode
from app.schemas.crud import CodeNodeCreate, CodeNodeUpdate


async def create_code_node(
    db: AsyncSession,
    body: CodeNodeCreate,
    actor_id: uuid.UUID,
) -> CodeNode:
    """Create a new code node and flush to DB."""
    node = CodeNode(
        path=body.path,
        node_type=body.node_type,
        label=body.label,
        project_id=body.project_id,
        metadata_=body.metadata,
        explored_by=actor_id,
    )
    db.add(node)
    await db.flush()
    await db.refresh(node)
    return node


async def get_code_node_by_id(db: AsyncSession, node_id: uuid.UUID) -> CodeNode:
    """Retrieve a code node by ID or raise 404."""
    result = await db.execute(select(CodeNode).where(CodeNode.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code-Node nicht gefunden")
    return node


async def update_code_node(
    db: AsyncSession,
    node_id: uuid.UUID,
    body: CodeNodeUpdate,
) -> CodeNode:
    """Partially update a code node and flush to DB."""
    node = await get_code_node_by_id(db, node_id)

    if body.label is not None:
        node.label = body.label
    if body.node_type is not None:
        node.node_type = body.node_type
    if body.metadata is not None:
        node.metadata_ = body.metadata

    await db.flush()
    await db.refresh(node)
    return node
