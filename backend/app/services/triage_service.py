"""Triage-Service — routing of [UNROUTED] events to Epics/Tasks + DLQ list.

Provides the business logic for manual triage decisions:
  - route_event: assign inbound event to an epic
  - ignore_event: dismiss event with optional reason
  - list_dead_letters_page: paginierte Dead-Letter-Liste (cursor-basiert)

Only events with routing_state='unrouted' can be routed/ignored (else 409).
Each decision is audit-logged and SSE-broadcast to /events/triage channel.
"""
from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import UTC, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sync import SyncDeadLetter, SyncOutbox
from app.services.audit import write_audit
from app.services import event_bus
from app.services.learning_artifacts import create_learning_artifact


class TriageConflictError(Exception):
    """Raised when event is not in 'unrouted' state."""

    def __init__(self, event_id: str, current_state: str):
        self.event_id = event_id
        self.current_state = current_state
        super().__init__(
            f"Event {event_id} has routing_state='{current_state}', expected 'unrouted'"
        )


class TriageNotFoundError(Exception):
    """Raised when event does not exist."""

    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Event {event_id} not found")


async def route_event(
    db: AsyncSession,
    event_id: str,
    epic_id: str,
    actor_id: uuid.UUID,
    actor_role: str = "admin",
) -> dict:
    """Route an unrouted event to a specific epic.

    Raises:
        TriageNotFoundError: event not found
        TriageConflictError: event not in 'unrouted' state
    """
    event = await _get_event(db, event_id)
    if event is None:
        raise TriageNotFoundError(event_id)
    if event.routing_state != "unrouted":
        raise TriageConflictError(event_id, event.routing_state)

    # Update routing state
    event.routing_state = "routed"
    # Store routing metadata in payload
    routing_meta = {
        "routed_to_epic_id": epic_id,
        "routed_by": str(actor_id),
        "routed_at": datetime.now(timezone.utc).isoformat(),
    }
    current_payload = dict(event.payload) if event.payload else {}
    current_payload["_routing"] = routing_meta
    event.payload = current_payload

    await db.flush()

    # Audit log
    await write_audit(
        tool_name="triage_route_event",
        actor_id=actor_id,
        actor_role=actor_role,
        input_payload={"event_id": event_id, "epic_id": epic_id},
        target_id=event_id,
    )

    # SSE broadcast
    event_bus.publish(
        "triage_routed",
        {"event_id": event_id, "epic_id": epic_id, "actor": str(actor_id)},
        channel="triage",
    )

    # Learning artifact: routing decision hint
    await create_learning_artifact(
        db,
        artifact_type="execution_learning",
        source_type="triage_decision",
        source_ref=event_id,
        summary=f"Routing-Hinweis: {event.entity_type} von {event.system} → Epic {epic_id}",
        detail={
            "kind": "routing_hint",
            "audiences": ["triage"],
            "decision": "routed",
            "entity_type": event.entity_type,
            "system": event.system,
            "epic_id": epic_id,
            "occurrence_count": 1,
            "source_refs": [event_id],
            "effectiveness": {},
        },
        agent_role=actor_role,
        project_id=str(event.project_id) if event.project_id else None,
        confidence=0.72,
        merge_on_duplicate=True,
    )

    await db.commit()
    return {
        "status": "routed",
        "event_id": event_id,
        "epic_id": epic_id,
    }


async def ignore_event(
    db: AsyncSession,
    event_id: str,
    actor_id: uuid.UUID,
    reason: str = "",
    actor_role: str = "admin",
) -> dict:
    """Ignore an unrouted event with optional reason.

    Raises:
        TriageNotFoundError: event not found
        TriageConflictError: event not in 'unrouted' state
    """
    event = await _get_event(db, event_id)
    if event is None:
        raise TriageNotFoundError(event_id)
    if event.routing_state != "unrouted":
        raise TriageConflictError(event_id, event.routing_state)

    # Update routing state
    event.routing_state = "ignored"
    if reason:
        current_payload = dict(event.payload) if event.payload else {}
        current_payload["_ignored_reason"] = reason
        event.payload = current_payload

    await db.flush()

    # Audit log
    await write_audit(
        tool_name="triage_ignore_event",
        actor_id=actor_id,
        actor_role=actor_role,
        input_payload={"event_id": event_id, "reason": reason},
        target_id=event_id,
    )

    # SSE broadcast
    event_bus.publish(
        "triage_ignored",
        {"event_id": event_id, "reason": reason, "actor": str(actor_id)},
        channel="triage",
    )

    # Learning artifact: ignore decision as routing hint (negative signal)
    if reason:
        await create_learning_artifact(
            db,
            artifact_type="execution_learning",
            source_type="triage_decision",
            source_ref=event_id,
            summary=f"Ignoriert: {event.entity_type} von {event.system} — {reason[:160]}",
            detail={
                "kind": "routing_hint",
                "audiences": ["triage"],
                "decision": "ignored",
                "entity_type": event.entity_type,
                "system": event.system,
                "ignore_reason": reason,
                "occurrence_count": 1,
                "source_refs": [event_id],
                "effectiveness": {},
            },
            agent_role=actor_role,
            project_id=str(event.project_id) if event.project_id else None,
            confidence=0.68,
            merge_on_duplicate=True,
        )

    await db.commit()
    return {
        "status": "ignored",
        "event_id": event_id,
        "reason": reason,
    }


async def _get_event(db: AsyncSession, event_id: str) -> SyncOutbox | None:
    """Fetch a sync_outbox entry by ID."""
    try:
        uid = uuid.UUID(event_id)
    except ValueError:
        return None
    stmt = select(SyncOutbox).where(SyncOutbox.id == uid)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ── Dead-Letter-Liste (cursor-basiert) ────────────────────────────────────────


def _payload_preview(payload: dict | None, max_length: int = 200) -> Optional[str]:
    if not payload:
        return None
    try:
        text = json.dumps(payload)
    except (TypeError, ValueError):
        text = str(payload)
    return text[:max_length] if len(text) <= max_length else f"{text[:max_length]}..."


def _encode_cursor(failed_at: Optional[datetime], dead_letter_id: uuid.UUID) -> str:
    payload = {
        "failed_at": failed_at.astimezone(UTC).isoformat() if failed_at else None,
        "id": str(dead_letter_id),
    }
    token = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(token).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[Optional[datetime], uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(f"{cursor}{padding}".encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        dead_letter_id = uuid.UUID(str(payload["id"]))

        failed_at_raw = payload.get("failed_at")
        if failed_at_raw is None:
            return None, dead_letter_id

        failed_at = datetime.fromisoformat(str(failed_at_raw).replace("Z", "+00:00"))
        if failed_at.tzinfo is None:
            failed_at = failed_at.replace(tzinfo=UTC)

        return failed_at, dead_letter_id
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc


def _apply_cursor(
    stmt,
    cursor_failed_at: Optional[datetime],
    cursor_id: uuid.UUID,
):
    if cursor_failed_at is None:
        return stmt.where(
            and_(
                SyncDeadLetter.failed_at.is_(None),
                SyncDeadLetter.id < cursor_id,
            )
        )

    return stmt.where(
        or_(
            SyncDeadLetter.failed_at.is_(None),
            SyncDeadLetter.failed_at < cursor_failed_at,
            and_(
                SyncDeadLetter.failed_at == cursor_failed_at,
                SyncDeadLetter.id < cursor_id,
            ),
        )
    )


async def list_dead_letters_page(
    db: AsyncSession,
    *,
    system: Optional[str] = None,
    direction: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 20,
) -> dict:
    """Paginierte Dead-Letter-Liste (cursor-basiert) für den Triage-Router.

    Returns dict mit: items, next_cursor, has_more, total, limit.
    """
    stmt = (
        select(SyncDeadLetter)
        .options(selectinload(SyncDeadLetter.outbox_entry))
        .where(
            SyncDeadLetter.discarded_at.is_(None),
            SyncDeadLetter.requeued_at.is_(None),
        )
    )
    count_stmt = (
        select(func.count())
        .select_from(SyncDeadLetter)
        .where(
            SyncDeadLetter.discarded_at.is_(None),
            SyncDeadLetter.requeued_at.is_(None),
        )
    )

    if direction:
        stmt = stmt.join(SyncDeadLetter.outbox_entry)
        count_stmt = count_stmt.join(SyncDeadLetter.outbox_entry)
        stmt = stmt.where(SyncOutbox.direction == direction)
        count_stmt = count_stmt.where(SyncOutbox.direction == direction)

    if system:
        stmt = stmt.where(SyncDeadLetter.system == system)
        count_stmt = count_stmt.where(SyncDeadLetter.system == system)

    if cursor:
        cursor_failed_at, cursor_id = _decode_cursor(cursor)
        stmt = _apply_cursor(stmt, cursor_failed_at, cursor_id)

    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar_one() or 0)

    rows_result = await db.execute(
        stmt.order_by(
            SyncDeadLetter.failed_at.desc().nullslast(),
            SyncDeadLetter.id.desc(),
        ).limit(limit + 1)
    )
    rows = rows_result.scalars().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items = [
        {
            "id": str(row.id),
            "system": row.system,
            "entity_type": row.entity_type,
            "attempts": int(getattr(getattr(row, "outbox_entry", None), "attempts", 0) or 0),
            "last_error": row.error,
            "error": row.error,
            "failed_at": row.failed_at,
            "requeued_at": row.requeued_at,
            "payload_preview": _payload_preview(row.payload),
        }
        for row in page_rows
    ]

    next_cursor = (
        _encode_cursor(page_rows[-1].failed_at, page_rows[-1].id)
        if has_more and page_rows
        else None
    )

    return {
        "items": items,
        "next_cursor": next_cursor,
        "has_more": has_more,
        "total": total,
        "limit": limit,
    }
