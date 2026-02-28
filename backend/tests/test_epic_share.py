"""Tests for POST /api/epics/{epic_key}/share — TASK-F-008."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_share_epic_creates_outbox_entry():
    """Share creates outbox entry with epic + tasks payload, returns 202 logic."""
    from app.routers.epics import share_epic
    from app.schemas.epic import EpicShareRequest

    epic_id = uuid.uuid4()
    peer_node_id = uuid.uuid4()
    task_id = uuid.uuid4()
    outbox_id = uuid.uuid4()

    epic = MagicMock()
    epic.id = epic_id
    epic.epic_key = "EPIC-TEST"
    epic.external_id = "EPIC-EXT"
    epic.state = "scoped"
    epic.title = "Test Epic"
    epic.description = "desc"
    epic.priority = "high"
    epic.dod_framework = {"criteria": ["a"]}

    peer = MagicMock()
    peer.id = peer_node_id
    peer.status = "active"
    peer.deleted_at = None

    task = MagicMock()
    task.id = task_id
    task.epic_id = epic_id
    task.task_key = "TASK-001"
    task.external_id = None
    task.title = "Task 1"
    task.description = "task desc"
    task.state = "incoming"
    task.definition_of_done = None
    task.pinned_skills = ["skill-a"]
    task.assigned_node_id = None

    db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = peer
        elif call_count == 2:
            r.scalars.return_value.all.return_value = [task]
        return r

    db.execute.side_effect = _execute

    async def _refresh(obj, *args, **kwargs):
        obj.id = outbox_id

    db.refresh.side_effect = _refresh

    body = EpicShareRequest(peer_node_id=peer_node_id)
    actor = MagicMock()
    actor.id = uuid.uuid4()
    actor.role = "admin"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.epic_service.EpicService.get_by_key",
            AsyncMock(return_value=epic),
        )
        result = await share_epic("EPIC-TEST", body, db, actor)

    assert result.outbox_id == outbox_id
    assert result.epic_key == "EPIC-TEST"
    assert result.peer_node_id == peer_node_id
    assert result.task_count == 1

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.entity_type == "epic_shared"
    assert added.direction == "peer_outbound"
    assert added.target_node_id == peer_node_id


@pytest.mark.asyncio
async def test_share_epic_bad_state_raises_400():
    """400 when epic state is not scoped or active."""
    from fastapi import HTTPException
    from app.routers.epics import share_epic
    from app.schemas.epic import EpicShareRequest

    epic = MagicMock()
    epic.state = "done"

    db = AsyncMock()
    body = EpicShareRequest(peer_node_id=uuid.uuid4())
    actor = MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.epic_service.EpicService.get_by_key",
            AsyncMock(return_value=epic),
        )
        with pytest.raises(HTTPException) as exc_info:
            await share_epic("EPIC-X", body, db, actor)

    assert exc_info.value.status_code == 400
    assert "scoped" in exc_info.value.detail


@pytest.mark.asyncio
async def test_share_epic_peer_not_found_raises_404():
    """404 when peer node doesn't exist."""
    from fastapi import HTTPException
    from app.routers.epics import share_epic
    from app.schemas.epic import EpicShareRequest

    epic = MagicMock()
    epic.state = "scoped"
    epic.id = uuid.uuid4()

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    db.execute.return_value = r

    body = EpicShareRequest(peer_node_id=uuid.uuid4())
    actor = MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.epic_service.EpicService.get_by_key",
            AsyncMock(return_value=epic),
        )
        with pytest.raises(HTTPException) as exc_info:
            await share_epic("EPIC-X", body, db, actor)

    assert exc_info.value.status_code == 404
    assert "Peer" in exc_info.value.detail


@pytest.mark.asyncio
async def test_share_epic_peer_inactive_raises_400():
    """400 when peer is not active."""
    from fastapi import HTTPException
    from app.routers.epics import share_epic
    from app.schemas.epic import EpicShareRequest

    epic = MagicMock()
    epic.state = "active"
    epic.id = uuid.uuid4()

    peer = MagicMock()
    peer.id = uuid.uuid4()
    peer.status = "offline"
    peer.deleted_at = None

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = peer
    db.execute.return_value = r

    body = EpicShareRequest(peer_node_id=peer.id)
    actor = MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.epic_service.EpicService.get_by_key",
            AsyncMock(return_value=epic),
        )
        with pytest.raises(HTTPException) as exc_info:
            await share_epic("EPIC-X", body, db, actor)

    assert exc_info.value.status_code == 400
    assert "not active" in exc_info.value.detail


@pytest.mark.asyncio
async def test_share_epic_assigns_selected_tasks():
    """When task_ids provided, assigned_node_id is set on those tasks."""
    from app.routers.epics import share_epic
    from app.schemas.epic import EpicShareRequest

    epic_id = uuid.uuid4()
    peer_node_id = uuid.uuid4()
    task1_id = uuid.uuid4()
    task2_id = uuid.uuid4()
    outbox_id = uuid.uuid4()

    epic = MagicMock()
    epic.id = epic_id
    epic.epic_key = "EPIC-ASSIGN"
    epic.external_id = None
    epic.state = "scoped"
    epic.title = "Assign Epic"
    epic.description = None
    epic.priority = "medium"
    epic.dod_framework = None

    peer = MagicMock()
    peer.id = peer_node_id
    peer.status = "active"
    peer.deleted_at = None

    task1 = MagicMock()
    task1.id = task1_id
    task1.epic_id = epic_id
    task1.task_key = "TASK-A"
    task1.external_id = None
    task1.title = "Task A"
    task1.description = None
    task1.state = "incoming"
    task1.definition_of_done = None
    task1.pinned_skills = []
    task1.assigned_node_id = None

    task2 = MagicMock()
    task2.id = task2_id
    task2.epic_id = epic_id
    task2.task_key = "TASK-B"
    task2.external_id = None
    task2.title = "Task B"
    task2.description = None
    task2.state = "incoming"
    task2.definition_of_done = None
    task2.pinned_skills = []
    task2.assigned_node_id = None

    db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = peer
        elif call_count == 2:
            r.scalars.return_value.all.return_value = [task1, task2]
        return r

    db.execute.side_effect = _execute

    async def _refresh(obj, *args, **kwargs):
        obj.id = outbox_id
    db.refresh.side_effect = _refresh

    body = EpicShareRequest(peer_node_id=peer_node_id, task_ids=[task1_id])
    actor = MagicMock()

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.epic_service.EpicService.get_by_key",
            AsyncMock(return_value=epic),
        )
        result = await share_epic("EPIC-ASSIGN", body, db, actor)

    assert result.task_count == 2
    assert task1.assigned_node_id == peer_node_id
    assert task2.assigned_node_id is None
