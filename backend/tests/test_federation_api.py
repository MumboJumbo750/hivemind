"""Unit-Tests for Federation Protocol API (TASK-F-004)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.federation import (
    FederatedEpicShare,
    FederatedSkillPublish,
    FederatedSyncRequest,
    FederatedTaskSpec,
    FederatedTaskUpdate,
    FederatedWikiPublish,
    PingResponse,
)


# ─── Schema validation tests ─────────────────────────────────────────────────


def test_ping_response_schema():
    resp = PingResponse(
        node_id=uuid.uuid4(),
        node_name="test-node",
        public_key="ed25519:pub:...",
    )
    assert resp.node_name == "test-node"
    assert resp.version == "0.1.0"


def test_skill_publish_schema():
    data = FederatedSkillPublish(
        title="FastAPI Auth",
        content="# Auth skill content",
        service_scope=["backend"],
        stack=["fastapi", "python"],
    )
    assert data.title == "FastAPI Auth"
    assert data.lifecycle == "active"
    assert data.skill_type == "domain"


def test_wiki_publish_schema():
    data = FederatedWikiPublish(
        title="Federation Concept",
        slug="federation-konzept",
        content="# Federation\nP2P nodes...",
        tags=["federation", "architecture"],
    )
    assert data.slug == "federation-konzept"


def test_epic_share_schema():
    data = FederatedEpicShare(
        title="Shared Epic",
        description="Cross-node epic",
        tasks=[
            FederatedTaskSpec(title="Task 1", description="Do thing 1"),
            FederatedTaskSpec(title="Task 2", state="scoped"),
        ],
    )
    assert len(data.tasks) == 2
    assert data.tasks[0].state == "incoming"
    assert data.tasks[1].state == "scoped"


def test_task_update_schema():
    data = FederatedTaskUpdate(
        external_id="TASK-F-001",
        state="done",
        result="Implementation complete",
    )
    assert data.external_id == "TASK-F-001"


def test_sync_request_schema():
    data = FederatedSyncRequest(
        items=[
            {"type": "skill", "payload": {"title": "Test", "content": "x", "service_scope": []}},
            {"type": "wiki", "payload": {"title": "Wiki", "slug": "wiki", "content": "y"}},
        ]
    )
    assert len(data.items) == 2
    assert data.items[0].type == "skill"


# ─── Router handler tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ping_handler():
    """Ping returns node identity."""
    from app.routers.federation import ping

    identity_mock = MagicMock()
    identity_mock.node_id = uuid.uuid4()
    identity_mock.node_name = "test-node"
    identity_mock.public_key = "ed25519:pub:test"

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = identity_mock
    db.execute.return_value = result_mock

    resp = await ping(db)
    assert resp.node_name == "test-node"
    assert resp.node_id == identity_mock.node_id


@pytest.mark.asyncio
async def test_skill_publish_creates_new_skill():
    """Skill publish creates a new federated skill."""
    from app.routers.federation import skill_publish

    body = FederatedSkillPublish(
        title="Test Skill",
        content="# Test content",
        service_scope=["backend"],
        stack=["python"],
    )

    request = MagicMock()
    origin_node_id = uuid.uuid4()
    request.state.federation_node_id = origin_node_id

    db = AsyncMock()
    # No existing skill found
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    # Mock refresh to populate id
    async def _refresh(obj, *args, **kwargs):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh.side_effect = _refresh

    resp = await skill_publish(body, request, db)

    db.add.assert_called_once()
    added_skill = db.add.call_args[0][0]
    assert added_skill.title == "Test Skill"
    assert added_skill.federation_scope == "federated"
    assert added_skill.origin_node_id == origin_node_id


@pytest.mark.asyncio
async def test_wiki_publish_creates_new_article():
    """Wiki publish creates a new federated article."""
    from app.routers.federation import wiki_publish

    body = FederatedWikiPublish(
        title="Fed Wiki",
        slug="fed-wiki",
        content="# Wiki content",
        tags=["test"],
    )

    request = MagicMock()
    origin_node_id = uuid.uuid4()
    request.state.federation_node_id = origin_node_id

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    db.execute.return_value = result_mock

    # Mock refresh to populate id
    async def _refresh(obj, *args, **kwargs):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh.side_effect = _refresh

    resp = await wiki_publish(body, request, db)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.title == "Fed Wiki"
    assert added.federation_scope == "federated"


@pytest.mark.asyncio
async def test_task_update_modifies_task():
    """Task update changes task state."""
    from app.routers.federation import task_update

    body = FederatedTaskUpdate(
        external_id="TASK-F-999",
        state="done",
        result="Complete",
    )

    request = MagicMock()
    origin_node_id = uuid.uuid4()
    request.state.federation_node_id = origin_node_id

    task_mock = MagicMock()
    task_mock.task_key = "TASK-999"
    task_mock.state = "in_progress"
    task_mock.assigned_node_id = origin_node_id  # matches sender
    task_mock.version = 1

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = task_mock
    db.execute.return_value = result_mock

    resp = await task_update(body, request, db)

    assert task_mock.state == "done"
    assert task_mock.result == "Complete"
    assert task_mock.version == 2
