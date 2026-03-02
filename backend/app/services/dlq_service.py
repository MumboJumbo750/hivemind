"""DLQ service — shared logic for MCP tools and REST endpoints (TASK-7-009).

Both ``hivemind/requeue_dead_letter`` and ``POST /api/triage/dead-letters/{id}/requeue``
delegate to this service to avoid code duplication.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sync import SyncDeadLetter, SyncOutbox
from app.services import event_bus


class DlqError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


async def requeue_dead_letter(
    db: AsyncSession,
    dead_letter_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> dict:
    """Create a new pending outbox entry from a dead letter.

    Returns a dict with the new outbox entry info.
    Raises DlqError on validation failures.
    """
    result = await db.execute(
        select(SyncDeadLetter)
        .options(selectinload(SyncDeadLetter.outbox_entry))
        .where(SyncDeadLetter.id == dead_letter_id)
    )
    dead_letter = result.scalar_one_or_none()

    if dead_letter is None:
        raise DlqError("ENTITY_NOT_FOUND", f"Dead letter '{dead_letter_id}' not found", 404)

    if dead_letter.requeued_at is not None:
        raise DlqError("CONFLICT", "Dead letter already requeued", 409)

    source = dead_letter.outbox_entry
    if source is None:
        raise DlqError("ENTITY_NOT_FOUND", "Source outbox entry not found", 404)

    new_outbox = SyncOutbox(
        direction=source.direction,
        system=dead_letter.system,
        target_node_id=source.target_node_id,
        entity_type=dead_letter.entity_type,
        entity_id=dead_letter.entity_id,
        payload=dead_letter.payload,
        raw_payload=source.raw_payload,
        attempts=0,
        next_retry_at=None,
        state="pending",
        routing_state=source.routing_state,
        embedding_model=source.embedding_model,
    )
    db.add(new_outbox)

    dead_letter.requeued_by = actor_id
    dead_letter.requeued_at = datetime.now(UTC)

    await db.flush()

    event_bus.publish(
        "dlq_requeued",
        {
            "dead_letter_id": str(dead_letter.id),
            "outbox_id": str(new_outbox.id),
            "system": dead_letter.system,
        },
        channel="triage",
    )
    event_bus.publish(
        "triage_dlq_updated",
        {
            "action": "requeued",
            "dead_letter_id": str(dead_letter.id),
            "outbox_id": str(new_outbox.id),
            "system": dead_letter.system,
        },
        channel="triage",
    )

    return {
        "id": str(dead_letter.id),
        "status": "requeued",
        "new_outbox_id": str(new_outbox.id),
        "requeued_by": str(actor_id),
        "requeued_at": dead_letter.requeued_at.isoformat(),
    }


async def discard_dead_letter(
    db: AsyncSession,
    dead_letter_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> dict:
    """Soft-discard a dead letter (sets discarded_at/by, keeps row for audit).

    Returns a dict with discard info.
    Raises DlqError on validation failures.
    """
    result = await db.execute(
        select(SyncDeadLetter).where(SyncDeadLetter.id == dead_letter_id)
    )
    dead_letter = result.scalar_one_or_none()

    if dead_letter is None:
        raise DlqError("ENTITY_NOT_FOUND", f"Dead letter '{dead_letter_id}' not found", 404)

    if dead_letter.discarded_at is not None:
        raise DlqError("CONFLICT", "Dead letter already discarded", 409)

    dead_letter.discarded_by = actor_id
    dead_letter.discarded_at = datetime.now(UTC)
    await db.flush()

    event_bus.publish(
        "dlq_discarded",
        {
            "dead_letter_id": str(dead_letter.id),
            "system": dead_letter.system,
        },
        channel="triage",
    )
    event_bus.publish(
        "triage_dlq_updated",
        {
            "action": "discarded",
            "dead_letter_id": str(dead_letter.id),
            "system": dead_letter.system,
        },
        channel="triage",
    )

    return {
        "id": str(dead_letter.id),
        "status": "discarded",
        "discarded_by": str(actor_id),
        "discarded_at": dead_letter.discarded_at.isoformat(),
    }
