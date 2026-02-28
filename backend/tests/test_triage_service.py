"""Tests for Triage Service — route_event, ignore_event, 409 conflict."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.triage_service import (
    TriageConflictError,
    TriageNotFoundError,
    ignore_event,
    route_event,
)


ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_event(routing_state: str = "unrouted", event_id: uuid.UUID | None = None):
    """Create a fake SyncOutbox-like object."""
    event = MagicMock()
    event.id = event_id or uuid.uuid4()
    event.routing_state = routing_state
    event.payload = {"source": "youtrack", "summary": "Test event"}
    return event


@pytest.mark.asyncio
async def test_route_event_success():
    event = _make_event("unrouted")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=event)))
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    with patch("app.services.triage_service.write_audit", new_callable=AsyncMock), \
         patch("app.services.triage_service.event_bus") as mock_bus:
        result = await route_event(db, str(event.id), "EPIC-PHASE-3", ADMIN_ID)

    assert result["status"] == "routed"
    assert result["epic_id"] == "EPIC-PHASE-3"
    assert event.routing_state == "routed"
    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][0] == "triage_routed"
    assert call_args[1]["channel"] == "triage"


@pytest.mark.asyncio
async def test_route_event_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    with pytest.raises(TriageNotFoundError):
        await route_event(db, str(uuid.uuid4()), "EPIC-1", ADMIN_ID)


@pytest.mark.asyncio
async def test_route_event_conflict():
    event = _make_event("routed")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=event)))

    with pytest.raises(TriageConflictError) as exc_info:
        await route_event(db, str(event.id), "EPIC-1", ADMIN_ID)
    assert exc_info.value.current_state == "routed"


@pytest.mark.asyncio
async def test_ignore_event_success():
    event = _make_event("unrouted")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=event)))
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    with patch("app.services.triage_service.write_audit", new_callable=AsyncMock), \
         patch("app.services.triage_service.event_bus") as mock_bus:
        result = await ignore_event(db, str(event.id), ADMIN_ID, reason="Not relevant")

    assert result["status"] == "ignored"
    assert result["reason"] == "Not relevant"
    assert event.routing_state == "ignored"
    mock_bus.publish.assert_called_once()
    call_args = mock_bus.publish.call_args
    assert call_args[0][0] == "triage_ignored"
    assert call_args[1]["channel"] == "triage"


@pytest.mark.asyncio
async def test_ignore_event_conflict_already_routed():
    event = _make_event("routed")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=event)))

    with pytest.raises(TriageConflictError):
        await ignore_event(db, str(event.id), ADMIN_ID)


@pytest.mark.asyncio
async def test_ignore_event_conflict_already_ignored():
    event = _make_event("ignored")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=event)))

    with pytest.raises(TriageConflictError):
        await ignore_event(db, str(event.id), ADMIN_ID)


@pytest.mark.asyncio
async def test_route_then_ignore_conflict():
    """After routing, ignoring should fail with 409."""
    event = _make_event("unrouted")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=event)))
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    with patch("app.services.triage_service.write_audit", new_callable=AsyncMock), \
         patch("app.services.triage_service.event_bus"):
        await route_event(db, str(event.id), "EPIC-1", ADMIN_ID)

    # Now event.routing_state == "routed"
    with pytest.raises(TriageConflictError):
        await ignore_event(db, str(event.id), ADMIN_ID)
