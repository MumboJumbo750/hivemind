from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.epic_run_scheduler import EpicRunSchedulerService


def _task(task_key: str, state: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        task_key=task_key,
        external_id=task_key,
        title=task_key,
        state=state,
        description="",
        artifacts=[],
        definition_of_done=None,
        quality_gate=None,
        qa_failed_count=0,
        result=None,
    )


@pytest.mark.asyncio
async def test_schedule_run_dispatches_up_to_effective_limit() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    scheduler = EpicRunSchedulerService(db)

    run = SimpleNamespace(
        id=uuid.uuid4(),
        dry_run=False,
        epic_id=uuid.uuid4(),
        config={
            "max_parallel_workers": 3,
            "resolved_execution_mode": "byoai",
            "execution_mode_preference": "byoai",
            "respect_file_claims": True,
        },
        status="started",
        analysis={},
        completed_at=None,
    )
    epic = SimpleNamespace(id=run.epic_id, project_id=uuid.uuid4())
    project = SimpleNamespace(id=uuid.uuid4(), slug="hivemind", workspace_root=None)
    tasks = [_task("TASK-1", "ready"), _task("TASK-2", "ready"), _task("TASK-3", "ready")]

    async def fake_transition(task_key, body, *, skip_conductor=False):
        del body
        assert skip_conductor is True
        for task in tasks:
            if task.task_key == task_key:
                task.state = "in_progress"
                return task
        raise AssertionError(f"unexpected task {task_key}")

    fake_task_service = SimpleNamespace(transition_state=AsyncMock(side_effect=fake_transition))

    scheduler._get_run = AsyncMock(return_value=run)
    scheduler._get_epic = AsyncMock(return_value=epic)
    scheduler._load_governance = AsyncMock(return_value={"review": "auto"})
    scheduler._load_scheduler_policy = AsyncMock(return_value={"role_limits": {"worker": 2}})
    scheduler.run_service._load_project = AsyncMock(return_value=project)
    scheduler.run_service._load_tasks = AsyncMock(side_effect=lambda epic_id: tasks)
    scheduler.run_service._load_open_decisions = AsyncMock(return_value=[])
    scheduler.run_service._load_active_task_dispatches = AsyncMock(return_value=[])

    with patch("app.services.epic_run_scheduler.TaskService", return_value=fake_task_service), \
         patch("app.services.conductor.conductor.dispatch", AsyncMock(return_value={"status": "byoai"})), \
         patch("app.services.epic_run_context.EpicRunContextService.ensure_epic_scratchpad", AsyncMock()), \
         patch("app.services.epic_run_context.EpicRunContextService.sync_file_claims", AsyncMock(return_value={"active": 2, "released": 0})), \
         patch("app.services.epic_run_context.EpicRunContextService.create_worker_handoff", AsyncMock()):
        result = await scheduler.schedule_run(run.id)

    assert result["status"] == "running"
    assert result["effective_max_parallel_workers"] == 2
    assert result["dispatched_task_keys"] == ["TASK-1", "TASK-2"]
    assert [task.state for task in tasks] == ["in_progress", "in_progress", "ready"]
    assert run.analysis["scheduler"]["effective_max_parallel_workers"] == 2
    assert run.analysis["execution_analysis"]["slot_plan"]["occupied_slots"] == 2


@pytest.mark.asyncio
async def test_schedule_run_pulls_next_task_when_capacity_frees() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    scheduler = EpicRunSchedulerService(db)

    run = SimpleNamespace(
        id=uuid.uuid4(),
        dry_run=False,
        epic_id=uuid.uuid4(),
        config={
            "max_parallel_workers": 1,
            "resolved_execution_mode": "byoai",
            "respect_file_claims": True,
        },
        status="running",
        analysis={},
        completed_at=None,
    )
    epic = SimpleNamespace(id=run.epic_id, project_id=uuid.uuid4())
    project = SimpleNamespace(id=uuid.uuid4(), slug="hivemind", workspace_root=None)
    tasks = [_task("TASK-ACTIVE", "in_progress"), _task("TASK-READY", "ready")]

    async def fake_transition(task_key, body, *, skip_conductor=False):
        del body
        assert skip_conductor is True
        for task in tasks:
            if task.task_key == task_key:
                task.state = "in_progress"
                return task
        raise AssertionError(f"unexpected task {task_key}")

    fake_task_service = SimpleNamespace(transition_state=AsyncMock(side_effect=fake_transition))

    scheduler._get_run = AsyncMock(return_value=run)
    scheduler._get_epic = AsyncMock(return_value=epic)
    scheduler._load_governance = AsyncMock(return_value={"review": "auto"})
    scheduler._load_scheduler_policy = AsyncMock(return_value={})
    scheduler.run_service._load_project = AsyncMock(return_value=project)
    scheduler.run_service._load_tasks = AsyncMock(side_effect=lambda epic_id: tasks)
    scheduler.run_service._load_open_decisions = AsyncMock(return_value=[])
    scheduler.run_service._load_active_task_dispatches = AsyncMock(return_value=[])

    with patch("app.services.epic_run_scheduler.TaskService", return_value=fake_task_service), \
         patch("app.services.conductor.conductor.dispatch", AsyncMock(return_value={"status": "byoai"})), \
         patch("app.services.epic_run_context.EpicRunContextService.ensure_epic_scratchpad", AsyncMock()), \
         patch("app.services.epic_run_context.EpicRunContextService.sync_file_claims", AsyncMock(return_value={"active": 1, "released": 0})), \
         patch("app.services.epic_run_context.EpicRunContextService.create_worker_handoff", AsyncMock()):
        first_result = await scheduler.schedule_run(run.id)
        tasks[0].state = "done"
        second_result = await scheduler.schedule_run(run.id)

    assert first_result["dispatched_task_keys"] == []
    assert second_result["dispatched_task_keys"] == ["TASK-READY"]
    assert tasks[1].state == "in_progress"


@pytest.mark.asyncio
async def test_schedule_run_marks_completed_when_all_tasks_terminal() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    scheduler = EpicRunSchedulerService(db)

    run = SimpleNamespace(
        id=uuid.uuid4(),
        dry_run=False,
        epic_id=uuid.uuid4(),
        config={"max_parallel_workers": 2, "resolved_execution_mode": "byoai"},
        status="running",
        analysis={},
        completed_at=None,
    )
    epic = SimpleNamespace(id=run.epic_id, project_id=uuid.uuid4())
    project = SimpleNamespace(id=uuid.uuid4(), slug="hivemind", workspace_root=None)
    tasks = [_task("TASK-1", "done"), _task("TASK-2", "cancelled")]

    scheduler._get_run = AsyncMock(return_value=run)
    scheduler._get_epic = AsyncMock(return_value=epic)
    scheduler._load_governance = AsyncMock(return_value={"review": "auto"})
    scheduler._load_scheduler_policy = AsyncMock(return_value={})
    scheduler.run_service._load_project = AsyncMock(return_value=project)
    scheduler.run_service._load_tasks = AsyncMock(side_effect=lambda epic_id: tasks)
    scheduler.run_service._load_open_decisions = AsyncMock(return_value=[])
    scheduler.run_service._load_active_task_dispatches = AsyncMock(return_value=[])

    with patch("app.services.epic_run_context.EpicRunContextService.ensure_epic_scratchpad", AsyncMock()), \
         patch("app.services.epic_run_context.EpicRunContextService.sync_file_claims", AsyncMock(return_value={"active": 0, "released": 0})):
        result = await scheduler.schedule_run(run.id)

    assert result["status"] == "completed"
    assert run.status == "completed"
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_schedule_run_auto_resumes_qa_failed_tasks_with_resume_package() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    scheduler = EpicRunSchedulerService(db)

    run = SimpleNamespace(
        id=uuid.uuid4(),
        dry_run=False,
        epic_id=uuid.uuid4(),
        config={
            "max_parallel_workers": 1,
            "resolved_execution_mode": "byoai",
            "respect_file_claims": True,
            "auto_resume_on_qa_failed": True,
        },
        status="running",
        analysis={},
        completed_at=None,
    )
    epic = SimpleNamespace(id=run.epic_id, project_id=uuid.uuid4())
    project = SimpleNamespace(id=uuid.uuid4(), slug="hivemind", workspace_root=None)
    tasks = [_task("TASK-RETRY", "qa_failed")]
    tasks[0].qa_failed_count = 1

    async def fake_reenter(task_key, *, skip_conductor=False):
        assert skip_conductor is True
        assert task_key == "TASK-RETRY"
        tasks[0].state = "in_progress"
        return tasks[0]

    fake_task_service = SimpleNamespace(
        transition_state=AsyncMock(),
        reenter_from_qa_failed=AsyncMock(side_effect=fake_reenter),
    )

    scheduler._get_run = AsyncMock(return_value=run)
    scheduler._get_epic = AsyncMock(return_value=epic)
    scheduler._load_governance = AsyncMock(return_value={"review": "auto"})
    scheduler._load_scheduler_policy = AsyncMock(return_value={})
    scheduler.run_service._load_project = AsyncMock(return_value=project)
    scheduler.run_service._load_tasks = AsyncMock(side_effect=lambda epic_id: tasks)
    scheduler.run_service._load_open_decisions = AsyncMock(return_value=[])
    scheduler.run_service._load_active_task_dispatches = AsyncMock(return_value=[])

    with patch("app.services.epic_run_scheduler.TaskService", return_value=fake_task_service), \
         patch("app.services.conductor.conductor.dispatch", AsyncMock(return_value={"status": "byoai"})) as dispatch, \
         patch("app.services.epic_run_context.EpicRunContextService.ensure_epic_scratchpad", AsyncMock()), \
         patch("app.services.epic_run_context.EpicRunContextService.sync_file_claims", AsyncMock(return_value={"active": 1, "released": 0})), \
         patch(
             "app.services.epic_run_context.EpicRunContextService.get_latest_resume_package",
             AsyncMock(return_value={"id": str(uuid.uuid4())}),
         ), \
         patch("app.services.epic_run_context.EpicRunContextService.create_worker_handoff", AsyncMock()) as create_handoff:
        result = await scheduler.schedule_run(run.id)

    assert result["status"] == "running"
    assert result["resumed_task_keys"] == ["TASK-RETRY"]
    assert tasks[0].state == "in_progress"
    dispatch.assert_awaited_once()
    create_handoff.assert_awaited_once()


@pytest.mark.asyncio
async def test_schedule_run_full_loop_handles_parallel_conflicts_and_resume() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    scheduler = EpicRunSchedulerService(db)

    run = SimpleNamespace(
        id=uuid.uuid4(),
        dry_run=False,
        epic_id=uuid.uuid4(),
        config={
            "max_parallel_workers": 3,
            "resolved_execution_mode": "byoai",
            "respect_file_claims": True,
            "auto_resume_on_qa_failed": True,
        },
        status="started",
        analysis={},
        completed_at=None,
    )
    epic = SimpleNamespace(id=run.epic_id, project_id=uuid.uuid4())
    project = SimpleNamespace(id=uuid.uuid4(), slug="hivemind", workspace_root=None)

    task_a = _task("TASK-A", "ready")
    task_a.artifacts = [
        {"kind": "file_claim", "path": "backend/app/services/a.py", "claim_type": "exclusive"}
    ]
    task_b = _task("TASK-B", "ready")
    task_c = _task("TASK-C", "ready")
    task_c.artifacts = [
        {"kind": "file_claim", "path": "backend/app/services/a.py", "claim_type": "exclusive"}
    ]
    task_d = _task("TASK-D", "ready")
    task_d.artifacts = [{"depends_on": ["TASK-A"]}]
    tasks = [task_a, task_b, task_c, task_d]

    async def fake_transition(task_key, body, *, skip_conductor=False):
        del body
        assert skip_conductor is True
        for task in tasks:
            if task.task_key == task_key:
                task.state = "in_progress"
                return task
        raise AssertionError(f"unexpected task {task_key}")

    async def fake_reenter(task_key, *, skip_conductor=False):
        assert skip_conductor is True
        for task in tasks:
            if task.task_key == task_key:
                task.state = "in_progress"
                return task
        raise AssertionError(f"unexpected resume task {task_key}")

    fake_task_service = SimpleNamespace(
        transition_state=AsyncMock(side_effect=fake_transition),
        reenter_from_qa_failed=AsyncMock(side_effect=fake_reenter),
    )

    scheduler._get_run = AsyncMock(return_value=run)
    scheduler._get_epic = AsyncMock(return_value=epic)
    scheduler._load_governance = AsyncMock(return_value={"review": "auto"})
    scheduler._load_scheduler_policy = AsyncMock(return_value={})
    scheduler.run_service._load_project = AsyncMock(return_value=project)
    scheduler.run_service._load_tasks = AsyncMock(side_effect=lambda epic_id: tasks)
    scheduler.run_service._load_open_decisions = AsyncMock(return_value=[])
    scheduler.run_service._load_active_task_dispatches = AsyncMock(return_value=[])

    with patch("app.services.epic_run_scheduler.TaskService", return_value=fake_task_service), \
         patch("app.services.conductor.conductor.dispatch", AsyncMock(return_value={"status": "byoai"})) as dispatch, \
         patch("app.services.epic_run_context.EpicRunContextService.ensure_epic_scratchpad", AsyncMock()), \
         patch("app.services.epic_run_context.EpicRunContextService.sync_file_claims", AsyncMock(return_value={"active": 2, "released": 1})), \
         patch("app.services.epic_run_context.EpicRunContextService.create_worker_handoff", AsyncMock()) as create_handoff, \
         patch(
             "app.services.epic_run_context.EpicRunContextService.get_latest_resume_package",
             AsyncMock(return_value={"id": str(uuid.uuid4()), "summary": "Retry with focused fix"}),
         ):
        first_result = await scheduler.schedule_run(run.id)
        assert first_result["dispatched_task_keys"] == ["TASK-A", "TASK-B"]
        assert [item["task_key"] for item in run.analysis["execution_analysis"]["conflicting"]] == ["TASK-C"]
        assert run.analysis["execution_analysis"]["waiting"][0]["task_key"] == "TASK-D"

        task_a.state = "done"
        task_b.state = "qa_failed"
        task_b.qa_failed_count = 1

        second_result = await scheduler.schedule_run(run.id)

    assert second_result["dispatched_task_keys"] == ["TASK-C", "TASK-D"]
    assert second_result["resumed_task_keys"] == ["TASK-B"]
    assert task_b.state == "in_progress"
    assert dispatch.await_count == 5
    assert create_handoff.await_count == 5
    assert run.analysis["scheduler"]["resumed_task_keys"] == ["TASK-B"]
    assert run.analysis["execution_analysis"]["slot_plan"]["occupied_slots"] == 3
