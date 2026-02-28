"""Skills Router — TASK-F-007 / F-013.

REST endpoints for skill management.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.federation import Node, NodeIdentity
from app.models.skill import Skill, SkillParent
from app.schemas.federation import FederatedSkillResponse

router = APIRouter(prefix="/skills", tags=["skills"])


# ─── List Schema ──────────────────────────────────────────────────────────────

class SkillListItem(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    service_scope: list[str] = []
    stack: list[str] = []
    skill_type: str
    lifecycle: str
    federation_scope: str
    origin_node_id: Optional[uuid.UUID] = None
    origin_node_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── List Skills ──────────────────────────────────────────────────────────────

@router.get("", response_model=list[SkillListItem])
async def list_skills(
    federation_scope: Optional[str] = Query(None, description="Filter by federation_scope (local|federated)"),
    db: AsyncSession = Depends(get_db),
) -> list[SkillListItem]:
    """List skills, optionally filtered by federation_scope."""
    query = select(Skill).where(Skill.deleted_at.is_(None))
    if federation_scope:
        query = query.where(Skill.federation_scope == federation_scope)
    query = query.order_by(Skill.title)

    result = await db.execute(query)
    skills = result.scalars().all()

    # Resolve node names
    node_ids = {s.origin_node_id for s in skills if s.origin_node_id}
    node_map: dict[uuid.UUID, str] = {}
    if node_ids:
        node_result = await db.execute(select(Node).where(Node.id.in_(node_ids)))
        for n in node_result.scalars().all():
            node_map[n.id] = n.node_name

    return [
        SkillListItem(
            id=s.id,
            title=s.title,
            content=s.content,
            service_scope=s.service_scope or [],
            stack=s.stack or [],
            skill_type=s.skill_type,
            lifecycle=s.lifecycle,
            federation_scope=s.federation_scope,
            origin_node_id=s.origin_node_id,
            origin_node_name=node_map.get(s.origin_node_id) if s.origin_node_id else None,
            created_at=s.created_at,
        )
        for s in skills
    ]


@router.post(
    "/{skill_id}/fork",
    response_model=FederatedSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def fork_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FederatedSkillResponse:
    """Fork a federated skill as a local draft.

    - Source skill must have federation_scope='federated'
    - Creates new local draft skill with extends link
    - Returns 409 if a fork already exists
    """
    # Load source skill
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden.")

    if source.federation_scope != "federated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur federierte Skills können geforkt werden.",
        )

    # Check if a fork already exists (same origin_skill via SkillParent)
    existing_fork = await db.execute(
        select(SkillParent).where(SkillParent.parent_id == skill_id)
    )
    if existing_fork.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Skill bereits als lokaler Draft vorhanden.",
        )

    # Get our own node_id
    identity_result = await db.execute(select(NodeIdentity))
    identity = identity_result.scalar_one_or_none()
    own_node_id = identity.node_id if identity else None

    # Create the forked skill
    forked = Skill(
        title=f"{source.title} (Fork)",
        content=source.content,
        service_scope=source.service_scope,
        stack=source.stack,
        skill_type=source.skill_type,
        lifecycle="draft",
        federation_scope="local",
        origin_node_id=own_node_id,
        version=1,
    )
    db.add(forked)
    await db.flush()

    # Create parent link
    parent_link = SkillParent(child_id=forked.id, parent_id=source.id)
    db.add(parent_link)
    await db.flush()
    await db.refresh(forked)

    return FederatedSkillResponse(
        id=forked.id,
        title=forked.title,
        origin_node_id=forked.origin_node_id,
        federation_scope=forked.federation_scope,
        created=True,
    )
