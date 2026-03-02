"""Tests for routing-threshold settings endpoints (TASK-7-007)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import get_db
from app.main import app
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor


def _result_with_row(row: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    return result


@pytest.mark.asyncio
async def test_get_routing_threshold_supports_hyphen_and_underscore_paths(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HIVEMIND_ROUTING_THRESHOLD", raising=False)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_with_row(None))

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        hyphen = await client.get("/api/settings/routing-threshold")
        underscore = await client.get("/api/settings/routing_threshold")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert hyphen.status_code == 200
    assert underscore.status_code == 200
    assert hyphen.json()["source"] == "db"
    assert underscore.json()["source"] == "db"


@pytest.mark.asyncio
async def test_get_routing_threshold_marks_env_source_when_env_is_explicitly_set(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HIVEMIND_ROUTING_THRESHOLD", "0.85")
    monkeypatch.setattr("app.config.settings.hivemind_routing_threshold", 0.85)

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_result_with_row(None))

    async def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    try:
        response = await client.get("/api/settings/routing_threshold")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "env"
    assert body["current_value"] == pytest.approx(0.85)
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_routing_threshold_underscore_validates_range(
    client: AsyncClient,
) -> None:
    response = await client.patch("/api/settings/routing_threshold", json={"value": 1.2})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_routing_threshold_denies_non_admin() -> None:
    async def _override_actor() -> CurrentActor:
        return CurrentActor(
            id=uuid.uuid4(),
            username="dev",
            role="developer",
        )

    db = AsyncMock()

    async def _override_db():
        yield db

    app.dependency_overrides[get_current_actor] = _override_actor
    app.dependency_overrides[get_db] = _override_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.patch("/api/settings/routing_threshold", json={"value": 0.42})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_routing_threshold_updates_timestamp_and_invalidates_cache() -> None:
    from app.routers.settings import RoutingThresholdUpdate, update_routing_threshold

    old_ts = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    row = SimpleNamespace(
        value="0.85",
        updated_at=old_ts,
        updated_by=None,
    )
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_result_with_row(row), _result_with_row(row)])
    db.flush = AsyncMock()

    actor = CurrentActor(id=uuid.uuid4(), username="admin", role="admin")

    with patch("app.routers.settings.write_audit", new=AsyncMock()) as write_audit:
        with patch("app.services.routing_service.invalidate_threshold_cache") as invalidate_cache:
            response = await update_routing_threshold(
                body=RoutingThresholdUpdate(value=0.73),
                db=db,
                actor=actor,
            )

    assert row.value == "0.73"
    assert row.updated_by == actor.id
    assert row.updated_at > old_ts
    write_audit.assert_awaited_once()
    invalidate_cache.assert_called_once()
    assert response.current_value == pytest.approx(0.73)
