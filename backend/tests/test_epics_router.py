from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.db import get_db
from app.main import app
from app.schemas.epic import EpicStartBlocker, EpicStartResponse


@pytest.mark.asyncio
async def test_start_epic_endpoint_returns_service_payload(client) -> None:
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db

    response_payload = EpicStartResponse(
        run_id=uuid.uuid4(),
        epic_key="EPIC-WORKER-ORCH",
        status="dry_run",
        dry_run=True,
        startable=False,
        epic_state="scoped",
        config={"max_parallel_workers": 2, "resolved_execution_mode": "byoai"},
        blockers=[EpicStartBlocker(code="TASKS_MISSING", message="Epic enthaelt noch keine Tasks.")],
        analysis={
            "workspace": {"workspace_root": "/workspace"},
            "task_summary": {"total": 0, "open": 0, "states": {}},
            "governance": {"review": "manual"},
            "worker_dispatch": {"resolved_mode": "byoai", "available": True},
        },
    )

    try:
        with pytest.MonkeyPatch.context() as mp:
            start_mock = AsyncMock(return_value=response_payload)
            audit_mock = AsyncMock()
            mp.setattr("app.services.epic_run_service.EpicRunService.start", start_mock)
            mp.setattr("app.routers.epics.write_audit", audit_mock)

            response = await client.post(
                "/api/epics/EPIC-WORKER-ORCH/start",
                json={
                    "dry_run": True,
                    "max_parallel_workers": 2,
                    "execution_mode_preference": "byoai",
                },
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "dry_run"
        assert payload["startable"] is False
        assert payload["blockers"][0]["code"] == "TASKS_MISSING"
        start_mock.assert_awaited_once()
        audit_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_list_epic_run_artifacts_endpoint_returns_service_payload(client) -> None:
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db

    run_id = uuid.uuid4()
    response_payload = [
        {
            "id": str(uuid.uuid4()),
            "epic_run_id": str(run_id),
            "epic_id": str(uuid.uuid4()),
            "task_id": None,
            "task_key": None,
            "artifact_type": "scratchpad",
            "state": "active",
            "source_role": "system",
            "target_role": None,
            "title": "Epic Scratchpad",
            "summary": "Gemeinsame Annahmen",
            "payload": {"assumptions": []},
            "created_at": "2026-03-07T12:00:00Z",
            "updated_at": "2026-03-07T12:00:00Z",
            "released_at": None,
        }
    ]

    try:
        with pytest.MonkeyPatch.context() as mp:
            verify_mock = AsyncMock()
            list_mock = AsyncMock(return_value=response_payload)
            mp.setattr("app.services.epic_run_context.EpicRunContextService.verify_run_access", verify_mock)
            mp.setattr("app.services.epic_run_context.EpicRunContextService.list_artifacts", list_mock)

            response = await client.get(f"/api/epic-runs/{run_id}/artifacts")

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["artifact_type"] == "scratchpad"
        verify_mock.assert_awaited_once()
        list_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_list_epic_runs_endpoint_returns_service_payload(client) -> None:
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db

    run_id = uuid.uuid4()
    response_payload = [
        {
            "id": str(run_id),
            "epic_id": str(uuid.uuid4()),
            "started_by": str(uuid.uuid4()),
            "status": "running",
            "dry_run": False,
            "config": {"max_parallel_workers": 2},
            "analysis": {"execution_analysis": {"summary": {"runnable": 1}}},
            "started_at": "2026-03-07T12:00:00Z",
            "completed_at": None,
        }
    ]

    try:
        with pytest.MonkeyPatch.context() as mp:
            list_mock = AsyncMock(return_value=response_payload)
            mp.setattr("app.services.epic_run_service.EpicRunService.list_runs", list_mock)

            response = await client.get("/api/epics/EPIC-WORKER-ORCH/runs")

        assert response.status_code == 200
        payload = response.json()
        assert payload[0]["status"] == "running"
        list_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_get_epic_run_endpoint_returns_service_payload(client) -> None:
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db

    run_id = uuid.uuid4()
    response_payload = {
        "id": str(run_id),
        "epic_id": str(uuid.uuid4()),
        "started_by": str(uuid.uuid4()),
        "status": "waiting",
        "dry_run": True,
        "config": {"max_parallel_workers": 3},
        "analysis": {"execution_analysis": {"summary": {"conflicting": 1}}},
        "started_at": "2026-03-07T12:00:00Z",
        "completed_at": "2026-03-07T12:00:02Z",
    }

    try:
        with pytest.MonkeyPatch.context() as mp:
            get_mock = AsyncMock(return_value=response_payload)
            mp.setattr("app.services.epic_run_service.EpicRunService.get_run", get_mock)

            response = await client.get(f"/api/epic-runs/{run_id}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["dry_run"] is True
        assert payload["status"] == "waiting"
        get_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
