"""Sync Outbox — list / query outbox entries.

Endpoints:
  GET /api/sync-outbox — List outbox entries with optional filters
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.sync import SyncOutbox

router = APIRouter(prefix="/sync-outbox", tags=["sync-outbox"])


@router.get("")
async def list_outbox_entries(
    direction: Optional[str] = Query(None, description="Filter by direction (inbound/outbound)"),
    routing_state: Optional[str] = Query(None, description="Filter by routing_state (unrouted/routed/ignored)"),
    system: Optional[str] = Query(None, description="Filter by source system"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    state: Optional[str] = Query(None, description="Filter by processing state"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List sync outbox entries with optional filters."""
    q = select(SyncOutbox).order_by(SyncOutbox.created_at.desc())

    if direction:
        q = q.where(SyncOutbox.direction == direction)
    if routing_state:
        q = q.where(SyncOutbox.routing_state == routing_state)
    if system:
        q = q.where(SyncOutbox.system == system)
    if entity_type:
        q = q.where(SyncOutbox.entity_type == entity_type)
    if state:
        q = q.where(SyncOutbox.state == state)

    q = q.offset(offset).limit(limit)
    result = await db.execute(q)
    entries = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "dedup_key": e.dedup_key,
            "direction": e.direction,
            "system": e.system,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "payload": e.payload,
            "state": e.state,
            "routing_state": e.routing_state,
            "attempts": e.attempts,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
