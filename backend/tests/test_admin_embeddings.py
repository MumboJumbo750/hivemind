from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException

from app.db import get_db
from app.main import app
from app.routers.admin import (
    RecomputeRequest,
    get_embedding_status,
    recompute_embeddings,
    _run_reembedding,
)
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor


def _actor(role: str = "admin") -> CurrentActor:
    return CurrentActor(
        id=uuid.uuid4(),
        username=role,
        role=role,
    )


def _scalar_result(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


class _SessionCtx:
    def __init__(self, db: "_FakeDbSession") -> None:
        self._db = db

    async def __aenter__(self) -> "_FakeDbSession":
        return self._db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeDbSession:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows
        self.executed_sql: list[tuple[str, dict | None]] = []
        self.commit = AsyncMock()

    async def execute(self, stmt, params=None):  # noqa: ANN001
        sql = str(stmt)
        self.executed_sql.append((sql, params))
        result = MagicMock()
        if sql.lstrip().upper().startswith("SELECT ID"):
            result.all.return_value = self._rows
        return result


def _set_override(key, value) -> object | None:  # noqa: ANN001
    old = app.dependency_overrides.get(key)
    app.dependency_overrides[key] = value
    return old


def _restore_override(key, old: object | None) -> None:  # noqa: ANN001
    if old is None:
        app.dependency_overrides.pop(key, None)
    else:
        app.dependency_overrides[key] = old


@pytest.mark.asyncio
async def test_get_embedding_status_returns_counts_per_entity() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(10),  # epics total
            _scalar_result(6),   # epics with embedding
            _scalar_result(4),   # skills total
            _scalar_result(1),   # skills with embedding
            _scalar_result(8),   # wiki total
            _scalar_result(8),   # wiki with embedding
            _scalar_result(3),   # docs total
            _scalar_result(2),   # docs with embedding
        ]
    )

    result = await get_embedding_status(db=db, actor=_actor("admin"))

    by_type = {item.entity_type: item for item in result.entities}
    assert by_type["epics"].total == 10
    assert by_type["epics"].with_embedding == 6
    assert by_type["epics"].without_embedding == 4
    assert by_type["skills"].total == 4
    assert by_type["skills"].with_embedding == 1
    assert by_type["skills"].without_embedding == 3
    assert by_type["wiki_articles"].total == 8
    assert by_type["wiki_articles"].with_embedding == 8
    assert by_type["wiki_articles"].without_embedding == 0
    assert by_type["docs"].total == 3
    assert by_type["docs"].with_embedding == 2
    assert by_type["docs"].without_embedding == 1


@pytest.mark.asyncio
async def test_recompute_embeddings_returns_job_id_and_schedules_background_task() -> None:
    bg = BackgroundTasks()

    response = await recompute_embeddings(
        body=RecomputeRequest(entity_types=["epics", "skills"], force=True),
        background_tasks=bg,
        actor=_actor("admin"),
    )

    assert uuid.UUID(response.job_id)
    assert response.entity_types == ["epics", "skills"]
    assert response.force is True
    assert len(bg.tasks) == 1
    assert bg.tasks[0].func.__name__ == "_run_reembedding"
    assert bg.tasks[0].kwargs["entity_types"] == ["epics", "skills"]
    assert bg.tasks[0].kwargs["force"] is True
    assert bg.tasks[0].kwargs["job_id"] == response.job_id


@pytest.mark.asyncio
async def test_recompute_embeddings_rejects_unknown_entity_types() -> None:
    bg = BackgroundTasks()
    with pytest.raises(HTTPException) as exc_info:
        await recompute_embeddings(
            body=RecomputeRequest(entity_types=["unknown"], force=False),
            background_tasks=bg,
            actor=_actor("admin"),
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("force", "expected_where"),
    [
        (False, "WHERE embedding IS NULL"),
        (True, ""),
    ],
)
async def test_run_reembedding_uses_skill_content_and_force_filter(
    force: bool,
    expected_where: str,
) -> None:
    db = _FakeDbSession(rows=[SimpleNamespace(id=uuid.uuid4(), txt="hello world")])

    with patch("app.routers.admin.AsyncSessionLocal", new=lambda: _SessionCtx(db)):
        with patch("app.services.embedding_service.EmbeddingService") as svc_cls:
            svc_cls.return_value.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
            with patch("app.routers.admin.event_bus.publish") as publish:
                await _run_reembedding(["skills"], force=force, job_id="job-1")

    select_sql = [sql for sql, _ in db.executed_sql if sql.lstrip().upper().startswith("SELECT ID")]
    assert len(select_sql) == 1
    assert "FROM skills" in select_sql[0]
    assert "COALESCE(content, '')" in select_sql[0]
    assert "COALESCE(description, '')" not in select_sql[0]
    if expected_where:
        assert expected_where in select_sql[0]
    else:
        assert "WHERE embedding IS NULL" not in select_sql[0]

    publish.assert_called_once()
    args, kwargs = publish.call_args
    assert args[0] == "reembedding_progress"
    assert args[1]["job_id"] == "job-1"
    assert args[1]["entity_type"] == "skills"
    assert args[1]["done"] == 1
    assert args[1]["total"] == 1
    assert kwargs["channel"] == "triage"


@pytest.mark.asyncio
async def test_embedding_admin_routes_deny_non_admin(client) -> None:
    async def _actor_dev() -> CurrentActor:
        return _actor("developer")

    async def _db_override():
        yield AsyncMock()

    old_actor = _set_override(get_current_actor, _actor_dev)
    old_db = _set_override(get_db, _db_override)
    try:
        status_resp = await client.get("/api/admin/embeddings/status")
        recompute_resp = await client.post(
            "/api/admin/embeddings/recompute",
            json={"entity_types": ["epics", "skills", "wiki_articles"], "force": False},
        )
    finally:
        _restore_override(get_current_actor, old_actor)
        _restore_override(get_db, old_db)

    assert status_resp.status_code == 403
    assert recompute_resp.status_code == 403
