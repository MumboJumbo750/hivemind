"""Nodes management router — TASK-F-012.

Provides endpoints for managing federation nodes:
- GET /api/node-identity — own node identity
- GET /api/nodes — list all peers
- POST /api/nodes — add a peer
- PATCH /api/nodes/{id} — update peer status
- DELETE /api/nodes/{id} — soft-delete a peer
- GET /api/settings/federation — federation config
- PATCH /api/settings/federation — update federation config
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime

from app.db import get_db
from app.models.federation import Node, NodeIdentity

router = APIRouter(tags=["nodes"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class NodeIdentityResponse(BaseModel):
    node_id: uuid.UUID
    node_name: str
    node_url: Optional[str] = None
    public_key: str

    model_config = {"from_attributes": True}


class PeerResponse(BaseModel):
    id: uuid.UUID
    node_name: str
    node_url: str
    public_key: Optional[str] = None
    status: str
    last_seen: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PeerCreate(BaseModel):
    node_name: str
    node_url: str
    public_key: Optional[str] = None


class PeerUpdate(BaseModel):
    status: Optional[str] = None
    node_name: Optional[str] = None


class FederationSettingsResponse(BaseModel):
    federation_enabled: bool
    topology: str
    hive_station_url: str
    hive_station_token: str
    hive_relay_enabled: bool
    heartbeat_interval: int
    peer_timeout: int


class FederationSettingsUpdate(BaseModel):
    federation_enabled: Optional[bool] = None
    topology: Optional[str] = None
    hive_station_url: Optional[str] = None
    hive_station_token: Optional[str] = None
    hive_relay_enabled: Optional[bool] = None


# ─── Node Identity ────────────────────────────────────────────────────────────

@router.get("/node-identity", response_model=NodeIdentityResponse)
async def get_node_identity(
    db: AsyncSession = Depends(get_db),
) -> NodeIdentityResponse:
    """Get the local node's identity."""
    result = await db.execute(select(NodeIdentity))
    identity = result.scalar_one_or_none()
    if identity is None:
        raise HTTPException(status_code=404, detail="Node identity not configured")

    node_result = await db.execute(select(Node).where(Node.id == identity.node_id))
    node = node_result.scalar_one_or_none()

    return NodeIdentityResponse(
        node_id=identity.node_id,
        node_name=identity.node_name,
        node_url=node.node_url if node else "",
        public_key=identity.public_key,
    )


# ─── Peer Management ─────────────────────────────────────────────────────────

@router.get("/nodes", response_model=list[PeerResponse])
async def list_nodes(
    db: AsyncSession = Depends(get_db),
) -> list[PeerResponse]:
    """List all known peer nodes (excluding soft-deleted)."""
    result = await db.execute(
        select(Node).where(Node.deleted_at.is_(None)).order_by(Node.node_name)
    )
    nodes = result.scalars().all()

    # Exclude own node
    identity_result = await db.execute(select(NodeIdentity))
    identity = identity_result.scalar_one_or_none()
    own_id = identity.node_id if identity else None

    return [
        PeerResponse(
            id=n.id,
            node_name=n.node_name,
            node_url=n.node_url,
            public_key=n.public_key,
            status=n.status,
            last_seen=n.last_seen,
        )
        for n in nodes
        if n.id != own_id
    ]


@router.post("/nodes", response_model=PeerResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    body: PeerCreate,
    db: AsyncSession = Depends(get_db),
) -> PeerResponse:
    """Add a new peer node."""
    # Check for duplicate URL
    existing = await db.execute(
        select(Node).where(Node.node_url == body.node_url)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A node with this URL already exists",
        )

    node = Node(
        node_name=body.node_name,
        node_url=body.node_url,
        public_key=body.public_key,
        status="active",
    )
    db.add(node)
    await db.flush()
    await db.refresh(node)
    await db.commit()

    return PeerResponse(
        id=node.id,
        node_name=node.node_name,
        node_url=node.node_url,
        public_key=node.public_key,
        status=node.status,
        last_seen=node.last_seen,
    )


@router.patch("/nodes/{node_id}", response_model=PeerResponse)
async def update_node(
    node_id: uuid.UUID,
    body: PeerUpdate,
    db: AsyncSession = Depends(get_db),
) -> PeerResponse:
    """Update a peer node's status or name."""
    result = await db.execute(
        select(Node).where(Node.id == node_id, Node.deleted_at.is_(None))
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    if body.status is not None:
        if body.status not in ("active", "inactive", "blocked"):
            raise HTTPException(status_code=400, detail="Invalid status")
        node.status = body.status
    if body.node_name is not None:
        node.node_name = body.node_name

    await db.flush()
    await db.refresh(node)
    await db.commit()

    return PeerResponse(
        id=node.id,
        node_name=node.node_name,
        node_url=node.node_url,
        public_key=node.public_key,
        status=node.status,
        last_seen=node.last_seen,
    )


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a peer node."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Node).where(Node.id == node_id, Node.deleted_at.is_(None))
    )
    node = result.scalar_one_or_none()
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    node.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()


# ─── Federation Settings ──────────────────────────────────────────────────────

@router.get("/settings/federation", response_model=FederationSettingsResponse)
async def get_federation_settings() -> FederationSettingsResponse:
    """Get current federation settings."""
    from app.config import settings

    return FederationSettingsResponse(
        federation_enabled=settings.hivemind_federation_enabled,
        topology=settings.hivemind_federation_topology,
        hive_station_url=settings.hivemind_hive_station_url,
        hive_station_token=settings.hivemind_hive_station_token,
        hive_relay_enabled=settings.hivemind_hive_relay_enabled,
        heartbeat_interval=settings.hivemind_heartbeat_interval,
        peer_timeout=settings.hivemind_peer_timeout,
    )


@router.patch("/settings/federation", response_model=FederationSettingsResponse)
async def update_federation_settings(
    body: FederationSettingsUpdate,
) -> FederationSettingsResponse:
    """Update federation settings (runtime-only, not persisted to env)."""
    from app.config import settings

    if body.federation_enabled is not None:
        settings.hivemind_federation_enabled = body.federation_enabled
    if body.topology is not None:
        if body.topology not in ("direct_mesh", "hub_assisted", "hub_relay"):
            raise HTTPException(status_code=400, detail="Invalid topology")
        settings.hivemind_federation_topology = body.topology
    if body.hive_station_url is not None:
        settings.hivemind_hive_station_url = body.hive_station_url
    if body.hive_station_token is not None:
        settings.hivemind_hive_station_token = body.hive_station_token
    if body.hive_relay_enabled is not None:
        settings.hivemind_hive_relay_enabled = body.hive_relay_enabled

    return FederationSettingsResponse(
        federation_enabled=settings.hivemind_federation_enabled,
        topology=settings.hivemind_federation_topology,
        hive_station_url=settings.hivemind_hive_station_url,
        hive_station_token=settings.hivemind_hive_station_token,
        hive_relay_enabled=settings.hivemind_hive_relay_enabled,
        heartbeat_interval=settings.hivemind_heartbeat_interval,
        peer_timeout=settings.hivemind_peer_timeout,
    )
