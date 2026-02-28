"""Unit-Tests for Federation Service (TASK-F-006 & TASK-F-009)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def _enable_federation(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", True)


@pytest.fixture
def _disable_federation(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", False)


@pytest.mark.asyncio
@pytest.mark.usefixtures("_disable_federation")
async def test_publish_skill_disabled():
    """No outbox entries when federation disabled."""
    from app.services.federation_service import publish_skill_to_federation

    db = AsyncMock()
    count = await publish_skill_to_federation(db, uuid.uuid4())
    assert count == 0
    db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_publish_skill_creates_outbox_entries():
    """Outbox entries created for each active peer."""
    from app.services.federation_service import publish_skill_to_federation

    skill_id = uuid.uuid4()
    own_node_id = uuid.uuid4()
    peer1_id = uuid.uuid4()
    peer2_id = uuid.uuid4()

    # Mock skill
    skill_mock = MagicMock()
    skill_mock.id = skill_id
    skill_mock.title = "Test Skill"
    skill_mock.content = "# Content"
    skill_mock.service_scope = ["backend"]
    skill_mock.stack = ["python"]
    skill_mock.skill_type = "domain"
    skill_mock.lifecycle = "active"
    skill_mock.federation_scope = "federated"
    skill_mock.version = 1

    # Mock identity
    identity_mock = MagicMock()
    identity_mock.node_id = own_node_id

    # Mock peers
    peer1 = MagicMock()
    peer1.id = peer1_id
    peer2 = MagicMock()
    peer2.id = peer2_id

    db = AsyncMock()
    call_count = 0

    def _execute_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            # Skill query
            result.scalar_one_or_none.return_value = skill_mock
        elif call_count == 2:
            # NodeIdentity query
            result.scalar_one_or_none.return_value = identity_mock
        elif call_count == 3:
            # Active peers query
            result.scalars.return_value.all.return_value = [peer1, peer2]
        else:
            # Dedup check — no existing
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _execute_side_effect

    count = await publish_skill_to_federation(db, skill_id)

    assert count == 2
    assert db.add.call_count == 2

    # Check outbox entries
    entries = [call[0][0] for call in db.add.call_args_list]
    assert entries[0].entity_type == "skill_published"
    assert entries[0].direction == "peer_outbound"
    assert entries[0].target_node_id == peer1_id
    assert entries[1].target_node_id == peer2_id


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_publish_skill_skips_non_federated():
    """Skills that are not federated/active are not published."""
    from app.services.federation_service import publish_skill_to_federation

    skill_mock = MagicMock()
    skill_mock.lifecycle = "draft"  # Not active
    skill_mock.federation_scope = "federated"

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = skill_mock
    db.execute.return_value = result_mock

    count = await publish_skill_to_federation(db, uuid.uuid4())
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("_disable_federation")
async def test_publish_wiki_disabled():
    """No outbox entries when federation disabled."""
    from app.services.federation_service import publish_wiki_to_federation

    db = AsyncMock()
    count = await publish_wiki_to_federation(db, uuid.uuid4())
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_notify_peer_task_update():
    """Outbox entry created for delegated task update."""
    from app.services.federation_service import notify_peer_task_update

    task_id = uuid.uuid4()
    assigned_node_id = uuid.uuid4()

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None  # no existing dedup
    db.execute.return_value = result_mock

    created = await notify_peer_task_update(
        db,
        task_id=task_id,
        task_key="TASK-999",
        new_state="done",
        assigned_node_id=assigned_node_id,
        result_text="Complete",
    )

    assert created is True
    db.add.assert_called_once()
    entry = db.add.call_args[0][0]
    assert entry.entity_type == "task_updated"
    assert entry.target_node_id == assigned_node_id
    assert entry.payload["state"] == "done"
