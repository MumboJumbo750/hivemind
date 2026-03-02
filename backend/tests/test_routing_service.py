"""Unit tests for pgvector auto-routing service (TASK-7-006)."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _session_ctx(db: AsyncMock) -> AsyncMock:
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=db)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


@pytest.mark.asyncio
async def test_route_bug_to_epic_above_threshold_assigns_and_emits_routed() -> None:
    from app.services import routing_service

    bug_report_id = uuid.uuid4()
    epic_id = uuid.uuid4()

    row = MagicMock()
    row.id = str(epic_id)
    row.score = 0.91

    report = MagicMock()

    vector_result = MagicMock()
    vector_result.first.return_value = row

    report_result = MagicMock()
    report_result.scalar_one_or_none.return_value = report

    db = AsyncMock()
    db.execute.side_effect = [vector_result, report_result]
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    with patch("app.services.routing_service._load_threshold", new=AsyncMock(return_value=0.85)):
        with patch.object(routing_service.EMBEDDING_SVC, "embed", new=AsyncMock(return_value=[0.1, 0.2])):
            with patch("app.services.routing_service.AsyncSessionLocal", return_value=_session_ctx(db)):
                with patch("app.services.routing_service.event_bus.publish") as publish:
                    result = await routing_service.route_bug_to_epic(
                        bug_report_id,
                        "NullPointerException in login flow",
                    )

    assert result.routed is True
    assert result.epic_id == epic_id
    assert report.epic_id == epic_id
    db.commit.assert_awaited_once()
    publish.assert_called_once()
    assert publish.call_args.args[0] == "bug_routed"
    assert publish.call_args.args[1]["bug_report_id"] == str(bug_report_id)
    assert publish.call_args.args[1]["epic_id"] == str(epic_id)
    assert publish.call_args.kwargs["channel"] == "triage"


@pytest.mark.asyncio
async def test_route_bug_to_epic_below_threshold_emits_unrouted() -> None:
    from app.services import routing_service

    bug_report_id = uuid.uuid4()
    epic_id = uuid.uuid4()

    row = MagicMock()
    row.id = str(epic_id)
    row.score = 0.42

    vector_result = MagicMock()
    vector_result.first.return_value = row

    db = AsyncMock()
    db.execute.side_effect = [vector_result]
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    with patch("app.services.routing_service._load_threshold", new=AsyncMock(return_value=0.85)):
        with patch.object(routing_service.EMBEDDING_SVC, "embed", new=AsyncMock(return_value=[0.1, 0.2])):
            with patch("app.services.routing_service.AsyncSessionLocal", return_value=_session_ctx(db)):
                with patch("app.services.routing_service.event_bus.publish") as publish:
                    result = await routing_service.route_bug_to_epic(bug_report_id, "minor ui issue")

    assert result.routed is False
    assert result.epic_id is None
    db.rollback.assert_awaited_once()
    publish.assert_called_once()
    assert publish.call_args.args[0] == "bug_unrouted"
    assert publish.call_args.args[1]["bug_report_id"] == str(bug_report_id)
    assert publish.call_args.args[1]["threshold"] == pytest.approx(0.85)
    assert publish.call_args.kwargs["channel"] == "triage"


@pytest.mark.asyncio
async def test_route_bug_to_epic_handles_embedding_unavailable() -> None:
    from app.services import routing_service

    bug_report_id = uuid.uuid4()

    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    with patch("app.services.routing_service._load_threshold", new=AsyncMock(return_value=0.80)):
        with patch.object(routing_service.EMBEDDING_SVC, "embed", new=AsyncMock(return_value=None)):
            with patch("app.services.routing_service.AsyncSessionLocal", return_value=_session_ctx(db)):
                with patch("app.services.routing_service.event_bus.publish") as publish:
                    result = await routing_service.route_bug_to_epic(bug_report_id, "Error in parser")

    assert result.routed is False
    assert result.epic_id is None
    assert result.score == pytest.approx(0.0)
    db.execute.assert_not_awaited()
    publish.assert_called_once()
    assert publish.call_args.args[0] == "bug_unrouted"
    assert publish.call_args.args[1]["reason"] == "embedding_unavailable"


@pytest.mark.asyncio
async def test_load_threshold_prefers_env_even_when_value_equals_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import routing_service

    monkeypatch.setenv("HIVEMIND_ROUTING_THRESHOLD", "0.85")
    monkeypatch.setattr("app.config.settings.hivemind_routing_threshold", 0.85)
    routing_service._threshold_cache.clear()
    monkeypatch.setattr(routing_service, "_threshold_cache_ts", 0.0)

    db = AsyncMock()
    db.execute = AsyncMock()

    threshold = await routing_service._load_threshold(db)

    assert threshold == pytest.approx(0.85)
    db.execute.assert_not_awaited()
