"""DLQ service — shared logic for MCP tools, REST endpoints and admin sync-status.

Both ``hivemind-requeue_dead_letter`` and ``POST /api/triage/dead-letters/{id}/requeue``
delegate to this service to avoid code duplication.

Admin-Query-Helfer (get_queue_stats, get_admin_*_rows) werden von admin.py genutzt,
um directe Model-Imports dort zu vermeiden.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, select
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


# ── Admin sync-status query helpers ──────────────────────────────────────────


async def get_queue_stats(db: AsyncSession, today_start: datetime) -> dict[str, int]:
    """Zähle Queue-Metriken für den Admin-Sync-Status-Endpoint.

    Returns dict mit Schlüsseln: pending_outbound, pending_inbound,
    dead_letters, delivered_today.
    """
    pending_outbound = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SyncOutbox)
                .where(SyncOutbox.direction == "outbound", SyncOutbox.state == "pending")
            )
        ).scalar_one()
        or 0
    )
    pending_inbound = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SyncOutbox)
                .where(
                    SyncOutbox.direction == "inbound",
                    SyncOutbox.state == "pending",
                    SyncOutbox.routing_state == "unrouted",
                )
            )
        ).scalar_one()
        or 0
    )
    dead_letters = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SyncDeadLetter)
                .where(SyncDeadLetter.discarded_at.is_(None))
            )
        ).scalar_one()
        or 0
    )
    delivered_today = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SyncOutbox)
                .where(
                    and_(
                        SyncOutbox.direction == "inbound",
                        SyncOutbox.routing_state == "routed",
                    ),
                    SyncOutbox.created_at >= today_start,
                )
            )
        ).scalar_one()
        or 0
    )
    return {
        "pending_outbound": pending_outbound,
        "pending_inbound": pending_inbound,
        "dead_letters": dead_letters,
        "delivered_today": delivered_today,
    }


async def get_admin_delivered_rows(db: AsyncSession, limit: int = 10) -> list[Any]:
    """Zuletzt zugestellte Inbound-Einträge für den Admin-Endpoint."""
    return list(
        (
            await db.execute(
                select(
                    SyncOutbox.id,
                    SyncOutbox.created_at,
                    SyncOutbox.direction,
                    SyncOutbox.entity_type,
                )
                .where(
                    SyncOutbox.direction == "inbound",
                    SyncOutbox.routing_state == "routed",
                )
                .order_by(SyncOutbox.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def get_admin_dead_letter_rows(db: AsyncSession, limit: int = 5) -> list[Any]:
    """Dead-Letter-Zeilen mit dem Outbox-Attempts-Count für den Admin-Endpoint."""
    return list(
        (
            await db.execute(
                select(
                    SyncDeadLetter.id,
                    SyncDeadLetter.failed_at,
                    SyncDeadLetter.error,
                    SyncOutbox.attempts,
                )
                .join(SyncOutbox, SyncOutbox.id == SyncDeadLetter.outbox_id, isouter=True)
                .where(SyncDeadLetter.discarded_at.is_(None))
                .order_by(SyncDeadLetter.failed_at.desc())
                .limit(limit)
            )
        ).all()
    )


async def get_admin_retry_rows(db: AsyncSession, limit: int = 5) -> list[Any]:
    """Outbox-Einträge mit mindestens einem fehlgeschlagenen Versuch für den Admin-Endpoint."""
    return list(
        (
            await db.execute(
                select(
                    SyncOutbox.id,
                    SyncOutbox.created_at,
                    SyncOutbox.attempts,
                )
                .where(
                    SyncOutbox.state == "pending",
                    SyncOutbox.attempts > 0,
                )
                .order_by(SyncOutbox.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
