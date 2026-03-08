"""Tests for the Learning Artifacts REST Router — TASK-AGENT-004.

Tests:
  - GET /api/learning/artifacts          — paginierte Liste
  - GET /api/learning/artifacts/{id}     — Einzel-Artefakt
  - GET /api/learning/stats              — Aggregate

Overrides FastAPI dependencies via app.dependency_overrides.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import get_db
from app.main import app


def _make_artifact(
    *,
    artifact_type: str = "execution_learning",
    status: str = "proposal",
    source_type: str = "worker_result",
    agent_role: str = "worker",
    summary: str = "Fixmuster: Tests gemeinsam mit Code anpassen",
    confidence: float = 0.80,
    kind: str = "fix_pattern",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        artifact_type=artifact_type,
        status=status,
        source_type=source_type,
        source_ref="TASK-1:v1:fix_pattern",
        source_dispatch_id=None,
        agent_role=agent_role,
        project_id=None,
        epic_id=None,
        task_id=None,
        summary=summary,
        detail={"kind": kind, "audiences": ["worker", "gaertner"]},
        confidence=confidence,
        fingerprint="fp-" + uuid.uuid4().hex,
        created_at=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
    )


def _override_db(mock_db):
    """Build a FastAPI dependency override that yields mock_db."""
    async def _dep():
        yield mock_db
    return _dep


# ── GET /api/learning/artifacts ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_learning_artifacts_returns_empty(client) -> None:
    artifact = _make_artifact()
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=0)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]
    )
    app.dependency_overrides[get_db] = _override_db(mock_db)
    try:
        response = await client.get("/api/learning/artifacts")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["total_count"] == 0


@pytest.mark.asyncio
async def test_list_learning_artifacts_returns_items(client) -> None:
    artifact = _make_artifact()
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=1)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[artifact])))),
        ]
    )
    app.dependency_overrides[get_db] = _override_db(mock_db)
    try:
        response = await client.get("/api/learning/artifacts")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert body["data"][0]["summary"] == artifact.summary


@pytest.mark.asyncio
async def test_list_learning_artifacts_filters_accepted(client) -> None:
    """Query params are forwarded without 422."""
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=0)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ]
    )
    app.dependency_overrides[get_db] = _override_db(mock_db)
    try:
        response = await client.get(
            "/api/learning/artifacts",
            params={"artifact_type": "execution_learning", "status": "proposal", "agent_role": "worker"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_learning_artifact_not_found(client) -> None:
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=None)
    app.dependency_overrides[get_db] = _override_db(mock_db)
    try:
        response = await client.get(f"/api/learning/artifacts/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_learning_artifact_found(client) -> None:
    artifact = _make_artifact()
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=artifact)
    app.dependency_overrides[get_db] = _override_db(mock_db)
    try:
        response = await client.get(f"/api/learning/artifacts/{artifact.id}")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == artifact.summary
    assert data["artifact_type"] == "execution_learning"


@pytest.mark.asyncio
async def test_learning_stats_returns_correct_structure(client) -> None:
    row = SimpleNamespace(artifact_type="execution_learning", status="proposal", count=7)
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[row])),
            MagicMock(scalar_one=MagicMock(return_value=3)),
        ]
    )
    app.dependency_overrides[get_db] = _override_db(mock_db)
    try:
        response = await client.get("/api/learning/stats")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 7
    assert body["skill_candidates"] == 3
    assert body["stats"][0]["artifact_type"] == "execution_learning"
