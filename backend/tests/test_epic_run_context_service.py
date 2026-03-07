from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.epic_run_context import EpicRunContextService


@pytest.mark.asyncio
async def test_get_worker_shared_context_filters_to_relevant_claims_and_handoffs() -> None:
    db = AsyncMock()
    svc = EpicRunContextService(db)

    run = SimpleNamespace(id=uuid.uuid4(), epic_id=uuid.uuid4())
    task = SimpleNamespace(
        id=uuid.uuid4(),
        epic_id=run.epic_id,
        task_key="TASK-1",
        title="Task 1",
        state="in_progress",
        artifacts=[
            {
                "kind": "file_claim",
                "path": "backend/app/services/epic_run_service.py",
                "claim_type": "exclusive",
            }
        ],
    )
    other_task_id = uuid.uuid4()

    scratchpad = SimpleNamespace(
        id=uuid.uuid4(),
        epic_run_id=run.id,
        epic_id=run.epic_id,
        task_id=None,
        artifact_type="scratchpad",
        state="active",
        source_role="system",
        target_role=None,
        title="Epic Scratchpad",
        summary="Gemeinsame Risiken",
        payload={"risks": ["Scheduler und Prompt muessen konsistent bleiben."]},
        created_at=None,
        updated_at=None,
        released_at=None,
    )
    handoff = SimpleNamespace(
        id=uuid.uuid4(),
        epic_run_id=run.id,
        epic_id=run.epic_id,
        task_id=task.id,
        artifact_type="handoff_note",
        state="active",
        source_role="system",
        target_role="worker",
        title="Handoff",
        summary="Bearbeite den Scheduler-Pfad zuerst.",
        payload={"task_key": task.task_key},
        created_at=None,
        updated_at=None,
        released_at=None,
    )
    resume_package = SimpleNamespace(
        id=uuid.uuid4(),
        epic_run_id=run.id,
        epic_id=run.epic_id,
        task_id=task.id,
        artifact_type="resume_package",
        state="active",
        source_role="reviewer",
        target_role="worker",
        title="Resume Paket",
        summary="QA #1: DoD noch offen",
        payload={
            "task_key": task.task_key,
            "open_dod_gaps": [{"criterion": "DoD 1", "status": "open"}],
            "changed_files": ["backend/app/services/epic_run_service.py"],
        },
        created_at=None,
        updated_at=None,
        released_at=None,
    )
    conflicting_claim = SimpleNamespace(
        id=uuid.uuid4(),
        epic_run_id=run.id,
        epic_id=run.epic_id,
        task_id=other_task_id,
        artifact_type="file_claim",
        state="active",
        source_role="worker",
        target_role=None,
        title="Claim",
        summary="TASK-2: exclusive backend/app/services/epic_run_service.py",
        payload={
            "task_key": "TASK-2",
            "task_state": "in_progress",
            "claims": [
                {
                    "paths": ["backend/app/services/epic_run_service.py"],
                    "claim_type": "exclusive",
                }
            ],
        },
        created_at=None,
        updated_at=None,
        released_at=None,
    )
    unrelated_claim = SimpleNamespace(
        id=uuid.uuid4(),
        epic_run_id=run.id,
        epic_id=run.epic_id,
        task_id=uuid.uuid4(),
        artifact_type="file_claim",
        state="active",
        source_role="worker",
        target_role=None,
        title="Claim",
        summary="TASK-3: exclusive frontend/src/App.vue",
        payload={
            "task_key": "TASK-3",
            "task_state": "in_progress",
            "claims": [{"paths": ["frontend/src/App.vue"], "claim_type": "exclusive"}],
        },
        created_at=None,
        updated_at=None,
        released_at=None,
    )

    svc._get_latest_run_for_epic = AsyncMock(return_value=run)
    svc.ensure_epic_scratchpad = AsyncMock()
    svc.sync_file_claims = AsyncMock()
    svc._load_run_artifacts = AsyncMock(
        return_value=[scratchpad, handoff, resume_package, conflicting_claim, unrelated_claim]
    )

    shared_context = await svc.get_worker_shared_context(task)

    assert shared_context["run_id"] == str(run.id)
    assert shared_context["scratchpad"][0]["summary"] == "Gemeinsame Risiken"
    assert shared_context["resume_package"]["summary"] == "QA #1: DoD noch offen"
    assert shared_context["handoffs"][0]["summary"] == "Bearbeite den Scheduler-Pfad zuerst."
    assert shared_context["file_claims"]["own_claims"][0]["paths"] == [
        "backend/app/services/epic_run_service.py"
    ]
    assert [item["task_key"] for item in shared_context["file_claims"]["active_related_claims"]] == [
        "TASK-2"
    ]


@pytest.mark.asyncio
async def test_sync_file_claims_releases_inactive_claims() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    svc = EpicRunContextService(db)

    run = SimpleNamespace(id=uuid.uuid4(), epic_id=uuid.uuid4())
    task = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-1",
        epic_id=run.epic_id,
        state="done",
        artifacts=[],
    )
    existing = SimpleNamespace(
        task_id=task.id,
        artifact_type="file_claim",
        state="active",
        released_at=None,
    )

    svc._get_run = AsyncMock(return_value=run)
    svc._load_epic_tasks = AsyncMock(return_value=[task])
    db.execute = AsyncMock(
        return_value=SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [existing])
        )
    )

    result = await svc.sync_file_claims(run.id)

    assert result == {"active": 0, "released": 1}
    assert existing.state == "released"
    assert existing.released_at is not None
