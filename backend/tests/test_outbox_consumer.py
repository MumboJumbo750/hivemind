"""Unit tests for outbox consumers (TASK-F-005 / TASK-7-002)."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.outbox_consumer import (
    EVENT_TYPE_TO_PATH,
    _dispatch_inbound,
    _move_to_dlq,
    _process_entry,
    process_inbound,
    process_outbound,
    process_outbox,
)
from app.services.sync_errors import PermanentSyncError


@pytest.fixture
def _enable_federation(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", True)
    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)
    monkeypatch.setattr(config.settings, "hivemind_outbox_interval", 30)


def _db_with_entries(entries: list[MagicMock]) -> AsyncMock:
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = entries

    db = AsyncMock()
    db.execute.return_value = result_mock
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    return db


def test_event_type_mapping() -> None:
    """All expected federation event types have URL paths."""
    assert "skill_published" in EVENT_TYPE_TO_PATH
    assert "wiki_published" in EVENT_TYPE_TO_PATH
    assert "epic_shared" in EVENT_TYPE_TO_PATH
    assert "task_updated" in EVENT_TYPE_TO_PATH


@pytest.mark.asyncio
async def test_process_outbox_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Federation outbox consumer is a no-op when federation is disabled."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", False)
    await process_outbox()


@pytest.mark.asyncio
async def test_process_outbound_not_gated_by_federation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outbound consumer runs even when federation is disabled."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", False)
    db = _db_with_entries([])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        await process_outbound()

    db.execute.assert_awaited_once()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_process_outbound_success_deletes_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Success path deletes the outbound outbox entry."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "youtrack"
    entry.attempts = 0
    entry.next_retry_at = None

    db = _db_with_entries([entry])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch("app.services.outbox_consumer._dispatch_outbound", new=AsyncMock()) as mock_dispatch:
            await process_outbound()

    statement = db.execute.call_args.args[0]
    for_update = getattr(statement, "_for_update_arg", None)
    assert for_update is not None
    assert getattr(for_update, "skip_locked", False) is True
    mock_dispatch.assert_awaited_once_with(entry)
    db.delete.assert_awaited_once_with(entry)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_outbound_retry_sets_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure path increments attempts and sets next_retry_at with exponential backoff."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "youtrack"
    entry.attempts = 0
    entry.next_retry_at = None

    db = _db_with_entries([entry])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.services.outbox_consumer._dispatch_outbound",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with patch("app.services.outbox_consumer._move_to_dlq", new=AsyncMock()) as move_to_dlq:
                await process_outbound()

    assert entry.attempts == 1
    assert entry.next_retry_at is not None
    delta_seconds = (entry.next_retry_at - datetime.now(UTC)).total_seconds()
    assert 110 <= delta_seconds <= 130
    move_to_dlq.assert_not_called()
    db.delete.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_outbound_moves_to_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    """Entry is promoted to DLQ when max attempts is reached."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "sentry"
    entry.attempts = 4
    entry.next_retry_at = None

    db = _db_with_entries([entry])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.services.outbox_consumer._dispatch_outbound",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with patch("app.services.outbox_consumer._move_to_dlq", new=AsyncMock()) as move_to_dlq:
                await process_outbound()

    assert entry.attempts == 5
    assert entry.next_retry_at is None
    move_to_dlq.assert_awaited_once_with(db, entry, "boom")
    db.delete.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_outbound_permanent_failure_goes_directly_to_dlq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Permanent failures (4xx) are sent to DLQ without retry backoff."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "youtrack"
    entry.attempts = 0
    entry.next_retry_at = None

    db = _db_with_entries([entry])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.services.outbox_consumer._dispatch_outbound",
            new=AsyncMock(side_effect=PermanentSyncError("http 404")),
        ):
            with patch("app.services.outbox_consumer._move_to_dlq", new=AsyncMock()) as move_to_dlq:
                await process_outbound()

    assert entry.attempts == 5
    assert entry.next_retry_at is None
    move_to_dlq.assert_awaited_once_with(db, entry, "http 404")
    db.delete.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_inbound_success_sets_routed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inbound success marks entry as routed and keeps audit row."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "sentry"
    entry.routing_state = "unrouted"
    entry.attempts = 0
    entry.next_retry_at = None

    db = _db_with_entries([entry])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.services.outbox_consumer._dispatch_inbound",
            new=AsyncMock(
                return_value={
                    "routing_state": "routed",
                    "intake_stage": "materialized",
                    "materialization": "bug_report",
                    "context_refs": {"task_keys": [], "epic_keys": []},
                    "reason": None,
                }
            ),
        ) as dispatch_inbound:
            await process_inbound()

    statement = db.execute.call_args.args[0]
    for_update = getattr(statement, "_for_update_arg", None)
    assert for_update is not None
    assert getattr(for_update, "skip_locked", False) is True
    dispatch_inbound.assert_awaited_once_with(entry, db)
    assert entry.routing_state == "routed"
    db.delete.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_inbound_retry_sets_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inbound failure increments attempts and sets next_retry_at."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "sentry"
    entry.routing_state = "unrouted"
    entry.attempts = 0
    entry.next_retry_at = None

    db = _db_with_entries([entry])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.services.outbox_consumer._dispatch_inbound",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with patch("app.services.outbox_consumer._move_to_dlq", new=AsyncMock()) as move_to_dlq:
                await process_inbound()

    assert entry.routing_state == "unrouted"
    assert entry.attempts == 1
    assert entry.next_retry_at is not None
    delta_seconds = (entry.next_retry_at - datetime.now(UTC)).total_seconds()
    assert 110 <= delta_seconds <= 130
    move_to_dlq.assert_not_called()
    db.delete.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_inbound_moves_to_dlq(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inbound entry is moved to DLQ at max attempts."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "youtrack"
    entry.routing_state = "unrouted"
    entry.attempts = 4
    entry.next_retry_at = None

    db = _db_with_entries([entry])

    with patch("app.services.outbox_consumer.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.services.outbox_consumer._dispatch_inbound",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            with patch("app.services.outbox_consumer._move_to_dlq", new=AsyncMock()) as move_to_dlq:
                await process_inbound()

    assert entry.routing_state == "unrouted"
    assert entry.attempts == 5
    assert entry.next_retry_at is None
    move_to_dlq.assert_awaited_once_with(db, entry, "boom")
    db.delete.assert_not_called()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_process_entry_success() -> None:
    """Successful peer delivery deletes outbox entry."""
    db = AsyncMock()

    target_node = MagicMock()
    target_node.status = "active"
    target_node.node_url = "http://peer:8000"
    target_node.node_name = "peer-node"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = target_node
    db.execute.return_value = result_mock

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.target_node_id = uuid.uuid4()
    entry.entity_type = "skill_published"
    entry.entity_id = str(uuid.uuid4())
    entry.payload = {"title": "Test Skill", "content": "x"}
    entry.attempts = 0

    response = MagicMock()
    response.status_code = 200
    client = AsyncMock()
    client.post.return_value = response

    with patch("app.services.outbox_consumer.sign_request", return_value=("node-id", "sig")):
        await _process_entry(db, client, entry)

    db.delete.assert_awaited_once_with(entry)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_process_entry_failure_increments_attempts() -> None:
    """Failed peer delivery increments attempts counter."""
    db = AsyncMock()

    target_node = MagicMock()
    target_node.status = "active"
    target_node.node_url = "http://peer:8000"
    target_node.node_name = "peer-node"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = target_node
    db.execute.return_value = result_mock

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.target_node_id = uuid.uuid4()
    entry.entity_type = "skill_published"
    entry.entity_id = str(uuid.uuid4())
    entry.payload = {"title": "Test", "content": "x"}
    entry.attempts = 0

    response = MagicMock()
    response.status_code = 500
    response.text = "Internal Server Error"
    client = AsyncMock()
    client.post.return_value = response

    with patch("app.services.outbox_consumer.sign_request", return_value=("node-id", "sig")):
        with patch("app.services.outbox_consumer.settings") as mock_settings:
            mock_settings.hivemind_dlq_max_attempts = 5
            await _process_entry(db, client, entry)

    assert entry.attempts == 1
    db.delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_process_entry_moves_to_dlq_at_max_attempts() -> None:
    """Peer entry moves to DLQ when max attempts is reached."""
    db = AsyncMock()

    target_node = MagicMock()
    target_node.status = "active"
    target_node.node_url = "http://peer:8000"
    target_node.node_name = "peer-node"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = target_node
    db.execute.return_value = result_mock
    db.add = MagicMock()

    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.target_node_id = uuid.uuid4()
    entry.entity_type = "skill_published"
    entry.entity_id = str(uuid.uuid4())
    entry.payload = {"title": "Test", "content": "x"}
    entry.system = "federation"
    entry.attempts = 4

    response = MagicMock()
    response.status_code = 500
    response.text = "Error"
    client = AsyncMock()
    client.post.return_value = response

    with patch("app.services.outbox_consumer.sign_request", return_value=("node-id", "sig")):
        with patch("app.services.outbox_consumer.settings") as mock_settings:
            mock_settings.hivemind_dlq_max_attempts = 5
            await _process_entry(db, client, entry)

    assert entry.attempts == 5
    assert entry.state == "dead_letter"
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_outbound_sentry_is_noop() -> None:
    """Sentry outbound dispatch is a no-op and does not raise."""
    from app.services.outbox_consumer import _dispatch_outbound

    entry = MagicMock()
    entry.system = "sentry"

    await _dispatch_outbound(entry)


@pytest.mark.asyncio
async def test_dispatch_inbound_sentry_prefers_raw_payload() -> None:
    """Inbound sentry dispatch uses raw_payload when available."""
    entry = MagicMock()
    entry.system = "sentry"
    entry.payload = {"source": "normalized"}
    entry.raw_payload = {"source": "raw"}

    service = MagicMock()
    service.process_sentry_event = AsyncMock()

    with patch("app.services.sentry_aggregation.SentryAggregationService", return_value=service):
        await _dispatch_inbound(entry, AsyncMock())

    service.process_sentry_event.assert_awaited_once_with({"source": "raw"})


@pytest.mark.asyncio
async def test_dispatch_inbound_sentry_falls_back_to_normalized_payload() -> None:
    """Inbound sentry dispatch falls back to entry.payload when raw payload is missing."""
    entry = MagicMock()
    entry.system = "sentry"
    entry.payload = {"source": "normalized"}
    entry.raw_payload = None

    service = MagicMock()
    service.process_sentry_event = AsyncMock()

    with patch("app.services.sentry_aggregation.SentryAggregationService", return_value=service):
        await _dispatch_inbound(entry, AsyncMock())

    service.process_sentry_event.assert_awaited_once_with({"source": "normalized"})


@pytest.mark.asyncio
async def test_move_to_dlq() -> None:
    """_move_to_dlq creates a dead letter entry and marks state."""
    db = AsyncMock()
    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "federation"
    entry.entity_type = "skill_published"
    entry.entity_id = "skill-123"
    entry.payload = {"test": True}
    db.add = MagicMock()

    await _move_to_dlq(db, entry, "Test error")

    db.add.assert_called_once()
    dlq = db.add.call_args[0][0]
    assert dlq.error == "Test error"
    assert entry.state == "dead_letter"
