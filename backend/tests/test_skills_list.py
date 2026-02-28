"""Tests for skills list endpoint — TASK-F-013."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.skills import list_skills


def _make_skill(title="Test Skill", scope="federated", node_id=None):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.title = title
    s.content = "Skill content"
    s.service_scope = ["backend"]
    s.stack = ["python"]
    s.skill_type = "domain"
    s.lifecycle = "active"
    s.federation_scope = scope
    s.origin_node_id = node_id or uuid.uuid4()
    s.deleted_at = None
    s.created_at = datetime.now(timezone.utc)
    return s


def _make_node(node_id, name="alpha"):
    n = MagicMock()
    n.id = node_id
    n.node_name = name
    return n


@pytest.mark.asyncio
async def test_list_skills_federated():
    node_id = uuid.uuid4()
    skill = _make_skill(node_id=node_id)
    node = _make_node(node_id, "alpha-node")

    db = AsyncMock()
    call_count = 0
    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalars.return_value.all.return_value = [skill]
        else:
            r.scalars.return_value.all.return_value = [node]
        return r
    db.execute = AsyncMock(side_effect=fake_execute)

    result = await list_skills(federation_scope="federated", db=db)
    assert len(result) == 1
    assert result[0].title == "Test Skill"
    assert result[0].origin_node_name == "alpha-node"


@pytest.mark.asyncio
async def test_list_skills_empty():
    db = AsyncMock()
    r = MagicMock()
    r.scalars.return_value.all.return_value = []
    db.execute.return_value = r

    result = await list_skills(federation_scope="federated", db=db)
    assert result == []


@pytest.mark.asyncio
async def test_list_skills_no_filter():
    skill = _make_skill(scope="local")

    db = AsyncMock()
    call_count = 0
    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalars.return_value.all.return_value = [skill]
        else:
            r.scalars.return_value.all.return_value = []
        return r
    db.execute = AsyncMock(side_effect=fake_execute)

    result = await list_skills(federation_scope=None, db=db)
    assert len(result) == 1
