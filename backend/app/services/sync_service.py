"""Sync-Service — gemeinsame Outbox-Queries für sync_outbox-Router und Webhook-Endpoints.

Kapselt alle direkten ``SyncOutbox``-Modell-Zugriffe, die bisher in den Routern
inline lagen, um Model-Imports aus den Routern zu entfernen.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import SyncOutbox


async def list_outbox_rows(
    db: AsyncSession,
    *,
    direction: Optional[str] = None,
    routing_state: Optional[str] = None,
    system: Optional[str] = None,
    entity_type: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Gefilterte, paginierte Outbox-Einträge als Liste von Dicts zurückgeben."""
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
            "project_id": str(e.project_id) if e.project_id else None,
            "integration_id": str(e.integration_id) if e.integration_id else None,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "payload": e.payload,
            "state": e.state,
            "routing_state": e.routing_state,
            "routing_detail": e.routing_detail,
            "attempts": e.attempts,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


async def get_outbox_by_dedup_key(db: AsyncSession, dedup_key: str) -> SyncOutbox | None:
    """Bestehenden Outbox-Eintrag per dedup_key suchen. Gibt None zurück wenn nicht gefunden."""
    result = await db.execute(
        select(SyncOutbox).where(SyncOutbox.dedup_key == dedup_key)
    )
    return result.scalar_one_or_none()


async def add_outbox_entry(db: AsyncSession, **fields: Any) -> SyncOutbox:
    """Neuen SyncOutbox-Eintrag anlegen, flushen und refreshen.

    Der Aufrufer ist verantwortlich für ``await db.commit()``.
    """
    entry = SyncOutbox(**fields)
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry
