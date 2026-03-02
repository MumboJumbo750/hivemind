"""Tests for triage DLQ router (TASK-7-009)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.db import get_db
from app.main import app
from app.routers.deps import get_current_actor
from app.routers.triage import discard_dead_letter_endpoint, list_dead_letters, requeue_dead_letter_endpoint
from app.schemas.auth import CurrentActor
from app.services.dlq_service import DlqError


def _count_result(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _rows_result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _actor(role: str = "admin") -> CurrentActor:
    return CurrentActor(
        id=uuid.uuid4(),
        username=role,
        role=role,
    )


def _make_dead_letter(*, ts: datetime, system: str = "youtrack") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        system=system,
        entity_type="youtrack_status_sync",
        error="HTTP 500",
        failed_at=ts,
        requeued_at=None,
        payload={"external_id": "YT-1"},
        outbox_entry=SimpleNamespace(attempts=5),
    )


def _mock_tx_db() -> AsyncMock:
    db = AsyncMock()
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=tx)
    return db


def _set_override(key, value) -> object | None:
    old = app.dependency_overrides.get(key)
    app.dependency_overrides[key] = value
    return old


def _restore_override(key, old: object | None) -> None:
    if old is None:
        app.dependency_overrides.pop(key, None)
    else:
        app.dependency_overrides[key] = old


@pytest.mark.asyncio
async def test_list_dead_letters_returns_cursor_paginated_result() -> None:
    now = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    rows = [
        _make_dead_letter(ts=now),
        _make_dead_letter(ts=now - timedelta(minutes=1)),
        _make_dead_letter(ts=now - timedelta(minutes=2)),
    ]

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_count_result(3), _rows_result(rows)])

    result = await list_dead_letters(
        system=None,
        direction=None,
        cursor=None,
        limit=2,
        db=db,
        actor=_actor("triage"),
    )

    assert len(result.items) == 2
    assert result.items[0].attempts == 5
    assert result.items[0].last_error == "HTTP 500"
    assert result.has_more is True
    assert result.next_cursor is not None
    assert result.total == 3
    assert result.limit == 2


@pytest.mark.asyncio
async def test_list_dead_letters_rejects_invalid_cursor() -> None:
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await list_dead_letters(
            system=None,
            direction=None,
            cursor="invalid-cursor",
            limit=20,
            db=db,
            actor=_actor("admin"),
        )

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_requeue_endpoint_maps_dlq_error_to_http_exception() -> None:
    db = _mock_tx_db()

    with patch(
        "app.routers.triage.requeue_dead_letter",
        new=AsyncMock(side_effect=DlqError("ENTITY_NOT_FOUND", "missing", 404)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await requeue_dead_letter_endpoint(
                dead_letter_id=uuid.uuid4(),
                db=db,
                actor=_actor("admin"),
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_discard_endpoint_maps_dlq_error_to_http_exception() -> None:
    db = _mock_tx_db()

    with patch(
        "app.routers.triage.discard_dead_letter",
        new=AsyncMock(side_effect=DlqError("CONFLICT", "already discarded", 409)),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await discard_dead_letter_endpoint(
                dead_letter_id=uuid.uuid4(),
                db=db,
                actor=_actor("triage"),
            )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_dead_letter_routes_forbid_non_admin_non_triage(client) -> None:
    async def _actor_dev() -> CurrentActor:
        return _actor("developer")

    async def _db_override():
        yield AsyncMock()

    old_actor = _set_override(get_current_actor, _actor_dev)
    old_db = _set_override(get_db, _db_override)

    try:
        list_resp = await client.get("/api/triage/dead-letters")
        requeue_resp = await client.post(f"/api/triage/dead-letters/{uuid.uuid4()}/requeue")
        discard_resp = await client.post(f"/api/triage/dead-letters/{uuid.uuid4()}/discard")
    finally:
        _restore_override(get_current_actor, old_actor)
        _restore_override(get_db, old_db)

    assert list_resp.status_code == 403
    assert requeue_resp.status_code == 403
    assert discard_resp.status_code == 403


@pytest.mark.asyncio
async def test_dead_letter_openapi_documents_cursor_and_item_fields(client) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200

    spec = resp.json()

    params = spec["paths"]["/api/triage/dead-letters"]["get"]["parameters"]
    param_names = {p["name"] for p in params}

    assert "cursor" in param_names
    assert "offset" not in param_names

    limit_schema = next(p["schema"] for p in params if p["name"] == "limit")
    assert limit_schema["maximum"] == 50

    item_props = spec["components"]["schemas"]["DeadLetterItem"]["properties"]
    assert "payload_preview" in item_props
    assert "attempts" in item_props
    assert "last_error" in item_props
    assert "error" in item_props
    assert "failed_at" in item_props
    assert "requeued_at" in item_props


@pytest.mark.asyncio
async def test_dead_letter_openapi_documents_typed_action_responses(client) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200

    spec = resp.json()

    requeue_schema = spec["paths"]["/api/triage/dead-letters/{dead_letter_id}/requeue"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    discard_schema = spec["paths"]["/api/triage/dead-letters/{dead_letter_id}/discard"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert "$ref" in requeue_schema
    assert "$ref" in discard_schema
