"""Sync Outbox — list / query outbox entries.

Endpoints:
  GET /api/sync-outbox — List outbox entries with optional filters
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.sync_service import list_outbox_rows

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
    return await list_outbox_rows(
        db,
        direction=direction,
        routing_state=routing_state,
        system=system,
        entity_type=entity_type,
        state=state,
        limit=limit,
        offset=offset,
    )
