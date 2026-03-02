"""Tests for skills list endpoint."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routers.skills import list_skills


def _make_skill(*, title: str = "Test Skill", scope: str = "federated") -> MagicMock:
    skill = MagicMock()
    skill.id = uuid.uuid4()
    skill.project_id = None
    skill.title = title
    skill.content = "Skill content"
    skill.service_scope = ["backend"]
    skill.stack = ["python"]
    skill.version_range = None
    skill.owner_id = None
    skill.proposed_by = None
    skill.confidence = None
    skill.skill_type = "domain"
    skill.lifecycle = "active"
    skill.version = 1
    skill.token_count = 42
    skill.rejection_rationale = None
    skill.federation_scope = scope
    skill.origin_node_id = uuid.uuid4()
    skill.created_at = datetime.now(timezone.utc)
    skill.updated_at = datetime.now(timezone.utc)
    return skill


def _result_with_count(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _result_with_rows(rows: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_list_skills_returns_items() -> None:
    skill = _make_skill(scope="federated")

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result_with_count(1), _result_with_rows([skill])])

    actor = MagicMock()
    response = await list_skills(
        project_id=None,
        lifecycle=None,
        service_scope=None,
        stack=None,
        skill_type=None,
        limit=50,
        offset=0,
        db=db,
        actor=actor,
    )

    assert response.total_count == 1
    assert len(response.data) == 1
    assert response.data[0].title == "Test Skill"
    assert response.data[0].federation_scope == "federated"


@pytest.mark.asyncio
async def test_list_skills_empty() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result_with_count(0), _result_with_rows([])])

    actor = MagicMock()
    response = await list_skills(
        project_id=None,
        lifecycle=None,
        service_scope=None,
        stack=None,
        skill_type=None,
        limit=50,
        offset=0,
        db=db,
        actor=actor,
    )

    assert response.total_count == 0
    assert response.data == []
    assert response.has_more is False


@pytest.mark.asyncio
async def test_list_skills_no_filter_includes_local() -> None:
    skill = _make_skill(scope="local")

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result_with_count(1), _result_with_rows([skill])])

    actor = MagicMock()
    response = await list_skills(
        project_id=None,
        lifecycle=None,
        service_scope=None,
        stack=None,
        skill_type=None,
        limit=50,
        offset=0,
        db=db,
        actor=actor,
    )

    assert len(response.data) == 1
    assert response.data[0].federation_scope == "local"
