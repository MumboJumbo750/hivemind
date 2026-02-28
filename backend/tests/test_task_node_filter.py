"""Tests for list_tasks node filter + assigned_node_name — TASK-F-014."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.epics import list_tasks


def _make_task(title="Test Task", assigned_node_id=None):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.task_key = f"TASK-{uuid.uuid4().hex[:4]}"
    t.epic_id = uuid.uuid4()
    t.parent_task_id = None
    t.title = title
    t.description = None
    t.state = "in_progress"
    t.version = 1
    t.definition_of_done = None
    t.assigned_to = None
    t.assigned_node_id = assigned_node_id
    t.pinned_skills = []
    t.result = None
    t.artifacts = []
    t.qa_failed_count = 0
    t.review_comment = None
    t.created_at = datetime.now(timezone.utc)
    t.updated_at = datetime.now(timezone.utc)
    return t


def _make_node(node_id, name="alpha"):
    n = MagicMock()
    n.id = node_id
    n.node_name = name
    return n


@pytest.mark.asyncio
async def test_list_tasks_resolves_node_name():
    """Tasks with assigned_node_id get assigned_node_name resolved."""
    node_id = uuid.uuid4()
    task = _make_task(assigned_node_id=node_id)
    node = _make_node(node_id, "beta-node")

    db = AsyncMock()
    call_count = 0
    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            # epic lookup
            epic = MagicMock()
            epic.id = task.epic_id
            r.scalar_one_or_none.return_value = epic
        elif call_count == 2:
            # task query
            r.scalars.return_value.all.return_value = [task]
        elif call_count == 3:
            # node lookup
            r.scalars.return_value.all.return_value = [node]
        return r
    db.execute = AsyncMock(side_effect=fake_execute)

    result = await list_tasks(
        epic_key="EPIC-1", state=None, assigned_node_id=None,
        limit=50, offset=0, db=db,
    )
    assert len(result) == 1
    assert result[0].assigned_node_name == "beta-node"
    assert result[0].assigned_node_id == node_id


@pytest.mark.asyncio
async def test_list_tasks_no_node():
    """Tasks without assigned_node_id have null node_name."""
    task = _make_task()

    db = AsyncMock()
    call_count = 0
    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            epic = MagicMock()
            epic.id = task.epic_id
            r.scalar_one_or_none.return_value = epic
        elif call_count == 2:
            r.scalars.return_value.all.return_value = [task]
        return r
    db.execute = AsyncMock(side_effect=fake_execute)

    result = await list_tasks(
        epic_key="EPIC-1", state=None, assigned_node_id=None,
        limit=50, offset=0, db=db,
    )
    assert len(result) == 1
    assert result[0].assigned_node_name is None
    assert result[0].assigned_node_id is None


@pytest.mark.asyncio
async def test_list_tasks_node_filter():
    """assigned_node_id filter narrows results (service level)."""
    node_id = uuid.uuid4()
    task_local = _make_task(title="Local Task")
    task_node = _make_task(title="Node Task", assigned_node_id=node_id)

    # We test only that the endpoint passes the parameter through
    # The actual filtering is in TaskService which is already tested
    db = AsyncMock()
    call_count = 0
    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            epic = MagicMock()
            epic.id = uuid.uuid4()
            r.scalar_one_or_none.return_value = epic
        elif call_count == 2:
            r.scalars.return_value.all.return_value = [task_node]
        elif call_count == 3:
            node = _make_node(node_id, "gamma")
            r.scalars.return_value.all.return_value = [node]
        return r
    db.execute = AsyncMock(side_effect=fake_execute)

    result = await list_tasks(
        epic_key="EPIC-1", state=None, assigned_node_id=node_id,
        limit=50, offset=0, db=db,
    )
    assert len(result) == 1
    assert result[0].title == "Node Task"
