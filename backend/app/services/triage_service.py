"""Triage-Service — routing of [UNROUTED] events to Epics/Tasks.

Provides the business logic for manual triage decisions:
  - route_event: assign inbound event to an epic
  - ignore_event: dismiss event with optional reason

Only events with routing_state='unrouted' can be routed/ignored (else 409).
Each decision is audit-logged and SSE-broadcast to /events/triage channel.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync import SyncOutbox
from app.services.audit import write_audit
from app.services import event_bus


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
