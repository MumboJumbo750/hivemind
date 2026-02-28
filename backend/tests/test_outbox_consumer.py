"""Unit-Tests for Outbox Consumer (TASK-F-005)."""
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.outbox_consumer import (
    EVENT_TYPE_TO_PATH,
    _move_to_dlq,
    _process_entry,
    process_outbox,
)


@pytest.fixture
def _enable_federation(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", True)
    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)
    monkeypatch.setattr(config.settings, "hivemind_outbox_interval", 30)


def test_event_type_mapping():
    """All expected event types have URL paths."""
    assert "skill_published" in EVENT_TYPE_TO_PATH
    assert "wiki_published" in EVENT_TYPE_TO_PATH
    assert "epic_shared" in EVENT_TYPE_TO_PATH
    assert "task_updated" in EVENT_TYPE_TO_PATH


@pytest.mark.asyncio
async def test_process_outbox_skips_when_disabled(monkeypatch):
    """Outbox consumer is a no-op when federation is disabled."""
    from app import config
    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", False)
    # Should return without doing anything
    await process_outbox()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_process_entry_success():
    """Successful delivery deletes outbox entry."""
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

    # Mock HTTP client with successful response
    response = MagicMock()
    response.status_code = 200
    client = AsyncMock()
    client.post.return_value = response

    # Mock sign_request
    with patch("app.services.outbox_consumer.sign_request", return_value=("node-id", "sig")):
        await _process_entry(db, client, entry)

    # Entry should be deleted
    db.delete.assert_awaited_once_with(entry)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_process_entry_failure_increments_attempts():
    """Failed delivery increments attempts counter."""
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

    # Mock HTTP client with failure
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
async def test_process_entry_moves_to_dlq_at_max_attempts():
    """Entry moves to DLQ when max attempts reached."""
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
    entry.system = "federation"
    entry.attempts = 4  # Will become 5 = max

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
    db.add.assert_called_once()  # DLQ entry added


@pytest.mark.asyncio
async def test_move_to_dlq():
    """_move_to_dlq creates dead letter entry."""
    db = AsyncMock()
    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.system = "federation"
    entry.entity_type = "skill_published"
    entry.entity_id = "skill-123"
    entry.payload = {"test": True}

    await _move_to_dlq(db, entry, "Test error")

    db.add.assert_called_once()
    dlq = db.add.call_args[0][0]
    assert dlq.error == "Test error"
    assert entry.state == "dead_letter"
