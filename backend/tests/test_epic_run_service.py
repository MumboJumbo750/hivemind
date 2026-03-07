from __future__ import annotations

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.auth import CurrentActor
from app.schemas.epic import EpicStartRequest
from app.services.epic_run_service import EpicRunService


def _actor(*, role: str = "admin", actor_id: uuid.UUID | None = None) -> CurrentActor:
    return CurrentActor(
        id=actor_id or uuid.uuid4(),
        username="tester",
        role=role,
    )


@pytest.mark.asyncio
async def test_start_epic_dry_run_persists_run_and_reports_blockers() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()

    epic = SimpleNamespace(
        id=uuid.uuid4(),
        epic_key="EPIC-WORKER-ORCH",
        project_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        backup_owner_id=None,
        state="scoped",
        version=0,
    )
    actor = _actor(actor_id=epic.owner_id)

    svc = EpicRunService(db)

    with patch("app.services.epic_run_service.EpicService.get_by_key", AsyncMock(return_value=epic)), \
         patch.object(svc, "_load_project", AsyncMock(return_value=None)), \
         patch.object(svc, "_load_tasks", AsyncMock(return_value=[])), \
         patch.object(svc, "_load_open_decisions", AsyncMock(return_value=[])), \
         patch.object(svc, "_load_active_task_dispatches", AsyncMock(return_value=[])), \
         patch.object(
             svc,
             "_resolve_worker_dispatch_mode",
             AsyncMock(return_value={"requested_mode": None, "resolved_mode": "local", "available": False, "reason": "Kein passender Worker-Dispatch-Modus verfuegbar."}),
         ), \
         patch("app.services.epic_run_service.get_governance", AsyncMock(return_value={"review": "manual"})):
        response = await svc.start(
            "EPIC-WORKER-ORCH",
            EpicStartRequest(dry_run=True),
            actor,
        )

    assert response.status == "dry_run"
    assert response.startable is False
    assert response.epic_state == "scoped"
    assert {blocker.code for blocker in response.blockers} == {
        "PROJECT_MISSING",
        "TASKS_MISSING",
        "WORKER_MODE_UNAVAILABLE",
    }
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_start_epic_real_run_sets_epic_in_progress() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()

    epic = SimpleNamespace(
        id=uuid.uuid4(),
        epic_key="EPIC-WORKER-ORCH",
        project_id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        backup_owner_id=None,
        state="scoped",
        version=2,
    )
    project = SimpleNamespace(
        id=uuid.uuid4(),
        repo_host_path="C:/projects/hivemind",
        workspace_root="/workspace",
        workspace_mode="read_write",
        onboarding_status="ready",
    )
    tasks = [
        SimpleNamespace(id=uuid.uuid4(), task_key="TASK-WORKER-001", state="incoming", title="Start"),
        SimpleNamespace(id=uuid.uuid4(), task_key="TASK-WORKER-002", state="ready", title="Plan"),
    ]
    actor = _actor(actor_id=epic.owner_id)

    svc = EpicRunService(db)

    with patch("app.services.epic_run_service.EpicService.get_by_key", AsyncMock(return_value=epic)), \
         patch.object(svc, "_load_project", AsyncMock(return_value=project)), \
         patch.object(svc, "_load_tasks", AsyncMock(return_value=tasks)), \
         patch.object(svc, "_load_open_decisions", AsyncMock(return_value=[])), \
         patch.object(svc, "_load_active_task_dispatches", AsyncMock(return_value=[])), \
         patch.object(
             svc,
             "_resolve_worker_dispatch_mode",
             AsyncMock(return_value={"requested_mode": "byoai", "resolved_mode": "byoai", "available": True, "reason": "mode_available"}),
         ), \
         patch("app.services.epic_run_context.EpicRunContextService.ensure_epic_scratchpad", AsyncMock()), \
         patch("app.services.epic_run_scheduler.EpicRunSchedulerService.schedule_run", AsyncMock(return_value={"status": "running"})), \
         patch("app.services.epic_run_service.get_governance", AsyncMock(return_value={"review": "manual", "epic_scoping": "manual"})):
        response = await svc.start(
            "EPIC-WORKER-ORCH",
            EpicStartRequest(
                dry_run=False,
                max_parallel_workers=2,
                execution_mode_preference="byoai",
            ),
            actor,
        )

    assert response.status == "running"
    assert response.startable is True
    assert response.config["resolved_execution_mode"] == "byoai"
    assert response.config["max_parallel_workers"] == 2
    assert epic.state == "in_progress"
    assert epic.version == 3
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_start_epic_rejects_non_owner_non_admin() -> None:
    db = AsyncMock()
    epic = SimpleNamespace(
        id=uuid.uuid4(),
        epic_key="EPIC-WORKER-ORCH",
        owner_id=uuid.uuid4(),
        backup_owner_id=None,
        state="scoped",
        version=0,
    )
    actor = _actor(role="developer")

    svc = EpicRunService(db)

    with patch("app.services.epic_run_service.EpicService.get_by_key", AsyncMock(return_value=epic)):
        with pytest.raises(HTTPException) as exc:
            await svc.start("EPIC-WORKER-ORCH", EpicStartRequest(dry_run=True), actor)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_execution_analysis_uses_dependencies_decisions_and_dispatches(
    tmp_path: Path,
) -> None:
    db = AsyncMock()
    svc = EpicRunService(db)

    seed_dir = tmp_path / "seed" / "tasks" / "epic-start-parallel-workers"
    seed_dir.mkdir(parents=True)
    (seed_dir / "TASK-WORKER-READY.json").write_text(
        json.dumps(
            {
                "external_id": "TASK-WORKER-READY",
                "depends_on": ["TASK-WORKER-DONE"],
            }
        ),
        encoding="utf-8",
    )

    project = SimpleNamespace(
        workspace_root=str(tmp_path),
        id=uuid.uuid4(),
        repo_host_path="C:/projects/hivemind",
        workspace_mode="read_write",
        onboarding_status="ready",
    )
    task_done = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-WORKER-DONE",
        external_id="TASK-WORKER-DONE",
        title="Done",
        state="done",
        description="",
        artifacts=[],
        definition_of_done=None,
        quality_gate=None,
    )
    task_ready = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-WORKER-READY",
        external_id="TASK-WORKER-READY",
        title="Ready",
        state="ready",
        description="",
        artifacts=[],
        definition_of_done=None,
        quality_gate=None,
    )
    task_waiting = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-WORKER-WAITING",
        external_id="TASK-WORKER-WAITING",
        title="Waiting",
        state="ready",
        description="",
        artifacts=[{"depends_on": ["TASK-WORKER-BLOCKER"]}],
        definition_of_done=None,
        quality_gate=None,
    )
    task_blocker = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-WORKER-BLOCKER",
        external_id="TASK-WORKER-BLOCKER",
        title="Blocker",
        state="scoped",
        description="",
        artifacts=[],
        definition_of_done=None,
        quality_gate=None,
    )
    task_decision = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-WORKER-DECISION",
        external_id="TASK-WORKER-DECISION",
        title="Decision",
        state="ready",
        description="",
        artifacts=[],
        definition_of_done=None,
        quality_gate=None,
    )
    task_active = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-WORKER-ACTIVE",
        external_id="TASK-WORKER-ACTIVE",
        title="Active",
        state="in_progress",
        description="",
        artifacts=[],
        definition_of_done=None,
        quality_gate=None,
    )

    open_decisions = [
        SimpleNamespace(
            id=uuid.uuid4(),
            task_id=task_decision.id,
            epic_id=None,
        )
    ]
    active_dispatches = [
        SimpleNamespace(
            id=uuid.uuid4(),
            trigger_id=task_decision.task_key,
            status="running",
        )
    ]

    analysis = svc._build_execution_analysis(
        project=project,
        tasks=[task_done, task_ready, task_waiting, task_blocker, task_decision, task_active],
        open_decisions=open_decisions,
        active_dispatches=active_dispatches,
        max_parallel_workers=2,
        respect_file_claims=True,
    )

    assert [item["task_key"] for item in analysis["runnable"]] == ["TASK-WORKER-READY"]
    assert any(
        item["task_key"] == "TASK-WORKER-WAITING"
        and item["reasons"][0]["code"] == "DEPENDENCIES_OPEN"
        for item in analysis["waiting"]
    )
    assert any(
        item["task_key"] == "TASK-WORKER-DECISION"
        and {reason["code"] for reason in item["reasons"]} == {"TASK_DECISION_OPEN", "DISPATCH_ALREADY_ACTIVE"}
        for item in analysis["blocked"]
    )
    assert any(
        item["task_key"] == "TASK-WORKER-ACTIVE"
        and item["reasons"][0]["code"] == "TASK_ALREADY_ACTIVE"
        for item in analysis["blocked"]
    )
    assert analysis["slot_plan"]["dispatch_now"] == ["TASK-WORKER-READY"]


@pytest.mark.asyncio
async def test_execution_analysis_marks_file_claim_conflicts() -> None:
    db = AsyncMock()
    svc = EpicRunService(db)

    project = SimpleNamespace(workspace_root=None)
    task_a = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-A",
        external_id="TASK-A",
        title="Task A",
        state="ready",
        description="",
        artifacts=[
            {
                "kind": "file_claim",
                "path": "backend/app/services/epic_run_service.py",
                "claim_type": "exclusive",
            }
        ],
        definition_of_done=None,
        quality_gate=None,
    )
    task_b = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-B",
        external_id="TASK-B",
        title="Task B",
        state="ready",
        description="",
        artifacts=[
            {
                "kind": "file_claim",
                "path": "backend/app/services/epic_run_service.py",
                "claim_type": "exclusive",
            }
        ],
        definition_of_done=None,
        quality_gate=None,
    )

    analysis = svc._build_execution_analysis(
        project=project,
        tasks=[task_a, task_b],
        open_decisions=[],
        active_dispatches=[],
        max_parallel_workers=2,
        respect_file_claims=True,
    )

    assert [item["task_key"] for item in analysis["runnable"]] == ["TASK-A"]
    assert [item["task_key"] for item in analysis["conflicting"]] == ["TASK-B"]
    assert analysis["conflicting"][0]["reasons"][0]["code"] == "FILE_CLAIM_CONFLICT"
