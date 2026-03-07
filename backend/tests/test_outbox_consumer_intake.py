from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.outbox_consumer import _dispatch_inbound


@pytest.mark.asyncio
async def test_dispatch_inbound_youtrack_returns_triage_pending() -> None:
    entry = MagicMock()
    entry.system = "youtrack"
    entry.project_id = uuid.uuid4()
    entry.payload = {"summary": "Investigate TASK-321"}

    db = AsyncMock()

    service = MagicMock()
    service.process_inbound = AsyncMock()

    with patch("app.services.youtrack_sync.YouTrackSyncService", return_value=service):
        outcome = await _dispatch_inbound(entry, db)

    assert outcome["routing_state"] == "unrouted"
    assert outcome["intake_stage"] == "triage_pending"


@pytest.mark.asyncio
async def test_dispatch_inbound_sentry_returns_materialized_outcome() -> None:
    entry = MagicMock()
    entry.system = "sentry"
    entry.project_id = uuid.uuid4()
    entry.payload = {"summary": "Crash"}
    entry.raw_payload = {"source": "raw"}

    db = AsyncMock()

    service = MagicMock()
    service.process_sentry_event = AsyncMock()

    with patch("app.services.sentry_aggregation.SentryAggregationService", return_value=service):
        outcome = await _dispatch_inbound(entry, db)

    assert outcome["routing_state"] == "routed"
    assert outcome["materialization"] == "bug_report"
