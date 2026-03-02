"""Unit tests for Sentry bug aggregation."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.node_bug_report import NodeBugReport
from app.services.sentry_aggregation import (
    SentryAggregationService,
    _compute_stack_trace_hash,
    _extract_sentry_issue_id,
)


def _session_ctx(db: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _db_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def test_extract_sentry_issue_id_supports_normalized_external_id() -> None:
    payload = {"external_id": "SENTRY-123"}
    assert _extract_sentry_issue_id(payload) == "SENTRY-123"


def test_extract_sentry_issue_id_prefers_nested_issue_id() -> None:
    payload = {
        "data": {
            "issue": {"id": "98765"},
            "event": {"id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
        }
    }
    assert _extract_sentry_issue_id(payload) == "98765"


def test_compute_stack_trace_hash_prefers_fingerprint() -> None:
    payload = {"fingerprint": ["{{ default }}", "NullPointerException"]}
    expected = hashlib.sha256(
        json.dumps(payload["fingerprint"], sort_keys=True).encode()
    ).hexdigest()
    assert _compute_stack_trace_hash(payload) == expected


def test_compute_stack_trace_hash_from_frames() -> None:
    payload = {
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {"filename": "backend/app/a.py", "function": "foo"},
                            {"filename": "backend/app/b.py", "function": "bar"},
                        ]
                    }
                }
            ]
        }
    }
    raw = json.dumps(
        [
            {"f": "backend/app/a.py", "fn": "foo"},
            {"f": "backend/app/b.py", "fn": "bar"},
        ],
        sort_keys=True,
    )
    expected = hashlib.sha256(raw.encode()).hexdigest()
    assert _compute_stack_trace_hash(payload) == expected


@pytest.mark.asyncio
async def test_upsert_by_sentry_issue_increments_existing_count() -> None:
    service = SentryAggregationService()
    now = datetime.now(UTC)
    existing = NodeBugReport(
        id=uuid.uuid4(),
        node_id=uuid.uuid4(),
        sentry_issue_id="SENTRY-INC-1",
        count=2,
        severity="warning",
        last_seen=now,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_db_result(existing))

    with patch("app.services.sentry_aggregation._find_code_node_id", new=AsyncMock(return_value=None)):
        report = await service._upsert_by_sentry_issue(
            db=db,
            sentry_issue_id="SENTRY-INC-1",
            stack_trace_hash="hash-1",
            first_seen=now,
            last_seen=now,
            severity="critical",
            raw_payload={"x": 1},
            file_paths=["backend/app/a.py"],
        )

    assert report is existing
    assert existing.count == 3
    assert existing.severity == "critical"
    assert existing.stack_trace_hash == "hash-1"


@pytest.mark.asyncio
async def test_upsert_by_sentry_issue_skips_insert_without_node_mapping() -> None:
    service = SentryAggregationService()
    now = datetime.now(UTC)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_db_result(None))
    db.add = MagicMock()
    db.flush = AsyncMock()

    with patch("app.services.sentry_aggregation._find_code_node_id", new=AsyncMock(return_value=None)):
        report = await service._upsert_by_sentry_issue(
            db=db,
            sentry_issue_id="SENTRY-NODELESS-1",
            stack_trace_hash="hash-1",
            first_seen=now,
            last_seen=now,
            severity="critical",
            raw_payload={"x": 1},
            file_paths=["backend/app/unknown.py"],
        )

    assert report is None
    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_sentry_event_routes_bug_report_after_upsert() -> None:
    service = SentryAggregationService()
    bug_report_id = uuid.uuid4()
    node_id = uuid.uuid4()
    bug_report = NodeBugReport(
        id=bug_report_id,
        node_id=node_id,
        sentry_issue_id="SENTRY-123",
        count=1,
        severity="critical",
    )

    payload = {
        "external_id": "SENTRY-123",
        "summary": "NullPointerException in auth middleware",
        "level": "error",
        "project": "core-api",
    }

    db = AsyncMock()
    db.commit = AsyncMock()

    with patch("app.services.sentry_aggregation.AsyncSessionLocal", return_value=_session_ctx(db)):
        with patch.object(service, "_upsert_by_sentry_issue", new=AsyncMock(return_value=bug_report)):
            with patch("app.services.routing_service.route_bug_to_epic", new=AsyncMock()) as route_bug:
                with patch("app.services.sentry_aggregation.event_bus.publish") as publish:
                    await service.process_sentry_event(payload)

    db.commit.assert_awaited_once()
    route_bug.assert_awaited_once()
    assert route_bug.await_args.args[0] == bug_report_id
    assert "NullPointerException" in route_bug.await_args.args[1]
    publish.assert_called_once()
    assert publish.call_args.args[0] == "bug_aggregated"
    assert publish.call_args.args[1]["bug_report_id"] == str(bug_report_id)
    assert publish.call_args.args[1]["node_id"] == str(node_id)
