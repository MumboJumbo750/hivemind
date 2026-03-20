"""E2E tests for the IDE dispatch lifecycle (TASK-AE2-001).

Tests the full dispatched → acknowledged → running → completed flow,
timeout/fallback behavior, progress events, and parallelism limits
using router-level calls with realistic dispatch objects.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.routers.conductor import (
    CompleteDispatchRequest,
    DispatchProgressRequest,
    acknowledge_ide_dispatch,
    complete_ide_dispatch,
    get_pending_ide_dispatches,
    mark_ide_dispatch_running,
    report_ide_dispatch_progress,
)
from app.services.dispatch_policy import EffectivePolicy, SkipReason


def _mock_db_with_dispatch(dispatch) -> AsyncMock:
    """Create a mock DB session that returns the given dispatch on execute."""
    db = AsyncMock()
    row = MagicMock()
    row.scalar_one_or_none.return_value = dispatch
    db.execute = AsyncMock(return_value=row)
    db.commit = AsyncMock()
    return db


def _make_dispatch(*, status="dispatched", dispatched_at=None, result=None):
    """Create a realistic dispatch SimpleNamespace."""
    return SimpleNamespace(
        id=uuid4(),
        trigger_type="task_state",
        trigger_id="TASK-E2E-001",
        trigger_detail="state:scoped->in_progress",
        agent_role="worker",
        prompt_type="worker_implement",
        execution_mode="ide",
        status=status,
        dispatched_at=dispatched_at or datetime.now(UTC),
        completed_at=None,
        result=result or {"prompt": "Implement the feature", "fallback_chain": ["ide", "local", "byoai"]},
    )


# ── Happy Path: dispatched → acknowledged → running → completed ──────────────

@pytest.mark.asyncio
async def test_ide_happy_path_full_lifecycle() -> None:
    """TASK-AE2-001: Full lifecycle dispatched → acknowledged → running → completed."""
    dispatch = _make_dispatch()
    dispatch_id = str(dispatch.id)
    db = _mock_db_with_dispatch(dispatch)

    # Step 1: Verify dispatch appears in pending list
    list_row = MagicMock()
    list_row.scalars.return_value.all.return_value = [dispatch]
    db_list = AsyncMock()
    db_list.execute = AsyncMock(return_value=list_row)

    pending = await get_pending_ide_dispatches(db=db_list, current_user=None)
    assert len(pending["data"]) == 1
    assert pending["data"][0]["dispatch_id"] == dispatch_id
    assert pending["data"][0]["status"] == "dispatched"
    assert pending["data"][0]["prompt"] == "Implement the feature"

    # Step 2: Acknowledge
    ack = await acknowledge_ide_dispatch(dispatch_id, db=db, current_user=None)
    assert ack["status"] == "acknowledged"
    assert dispatch.status == "acknowledged"
    assert "acknowledged_at" in dispatch.result

    # Step 3: Running
    run = await mark_ide_dispatch_running(dispatch_id, db=db, current_user=None)
    assert run["status"] == "running"
    assert dispatch.status == "running"
    assert "running_at" in dispatch.result

    # Step 4: Complete
    done = await complete_ide_dispatch(
        dispatch_id,
        body=CompleteDispatchRequest(status="completed", result="All tests pass"),
        db=db,
        current_user=None,
    )
    assert done["status"] == "completed"
    assert dispatch.status == "completed"
    assert dispatch.completed_at is not None
    assert dispatch.result["result"] == "All tests pass"


# ── Timeout: dispatched → timeout → fallback ─────────────────────────────────

@pytest.mark.asyncio
async def test_ide_timeout_triggers_fallback_dispatch() -> None:
    """TASK-AE2-001: Stale dispatch times out and re-dispatches via fallback chain."""
    from app.services.conductor_ide_timeout import ide_timeout_job

    stale_dispatch = _make_dispatch(
        dispatched_at=datetime.now(UTC) - timedelta(seconds=400),
        result={"fallback_chain": ["ide", "local", "byoai"]},
    )

    row = MagicMock()
    row.scalars.return_value.all.return_value = [stale_dispatch]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=row)
    db.commit = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.conductor_ide_timeout.AsyncSessionLocal", MagicMock(return_value=db)), \
         patch.object(settings, "hivemind_conductor_ide_timeout", 300), \
         patch.object(settings, "hivemind_conductor_ide_timeout_seconds", 300), \
         patch("app.services.conductor_ide_timeout.conductor.dispatch", new_callable=AsyncMock) as mock_dispatch:
        await ide_timeout_job()

    # Dispatch should be timed out
    assert stale_dispatch.status == "timed_out"
    assert stale_dispatch.completed_at is not None
    assert stale_dispatch.result["error"] == "IDE dispatch timed out - no acknowledgement received"
    assert stale_dispatch.result["timeout_seconds"] == 300

    # Fallback should have been dispatched with next mode in chain
    mock_dispatch.assert_called_once()
    kwargs = mock_dispatch.call_args.kwargs
    assert kwargs["execution_mode"] == "local"
    assert kwargs["fallback_chain"] == ["local", "byoai"]
    assert kwargs["trigger_id"] == "TASK-E2E-001"


@pytest.mark.asyncio
async def test_ide_timeout_no_stale_dispatches_is_noop() -> None:
    """TASK-AE2-001: Timeout job with no stale dispatches does nothing."""
    from app.services.conductor_ide_timeout import ide_timeout_job

    row = MagicMock()
    row.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(return_value=row)
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.conductor_ide_timeout.AsyncSessionLocal", MagicMock(return_value=db)), \
         patch.object(settings, "hivemind_conductor_ide_timeout_seconds", 300), \
         patch("app.services.conductor_ide_timeout.conductor.dispatch", new_callable=AsyncMock) as mock_dispatch:
        await ide_timeout_job()

    mock_dispatch.assert_not_called()


# ── Progress: Events during running ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_ide_progress_events_accumulate() -> None:
    """TASK-AE2-001: Progress events accumulate in dispatch result payload."""
    dispatch = _make_dispatch(status="running")
    dispatch.result["running_at"] = datetime.now(UTC).isoformat()
    dispatch_id = str(dispatch.id)
    db = _mock_db_with_dispatch(dispatch)

    # Send 3 progress events
    for i, (stage, msg) in enumerate([
        ("mcp_call", "hivemind-get_task"),
        ("mcp_call", "hivemind-fs_read"),
        ("mcp_call", "hivemind-submit_result"),
    ]):
        result = await report_ide_dispatch_progress(
            dispatch_id,
            body=DispatchProgressRequest(stage=stage, message=msg),
            db=db,
            current_user=None,
        )
        assert result["progress_count"] == i + 1

    # Verify all 3 progress entries
    progress = dispatch.result["progress"]
    assert len(progress) == 3
    assert progress[0]["message"] == "hivemind-get_task"
    assert progress[1]["message"] == "hivemind-fs_read"
    assert progress[2]["message"] == "hivemind-submit_result"
    assert "last_progress_at" in dispatch.result


@pytest.mark.asyncio
async def test_ide_progress_auto_transitions_to_running() -> None:
    """TASK-AE2-001: Progress on dispatched state auto-transitions to running."""
    dispatch = _make_dispatch(status="dispatched")
    dispatch_id = str(dispatch.id)
    db = _mock_db_with_dispatch(dispatch)

    result = await report_ide_dispatch_progress(
        dispatch_id,
        body=DispatchProgressRequest(stage="init", message="starting"),
        db=db,
        current_user=None,
    )

    assert result["status"] == "running"
    assert dispatch.status == "running"
    assert "running_at" in dispatch.result


@pytest.mark.asyncio
async def test_ide_progress_with_details() -> None:
    """TASK-AE2-001: Progress events can include structured details."""
    dispatch = _make_dispatch(status="running")
    dispatch_id = str(dispatch.id)
    db = _mock_db_with_dispatch(dispatch)

    details = {"tool": "hivemind-fs_read", "args": {"path": "/src/main.py"}, "duration_ms": 42}
    result = await report_ide_dispatch_progress(
        dispatch_id,
        body=DispatchProgressRequest(stage="mcp_call", message="reading file", details=details),
        db=db,
        current_user=None,
    )

    assert result["progress_count"] == 1
    entry = dispatch.result["progress"][0]
    assert entry["details"]["tool"] == "hivemind-fs_read"
    assert entry["details"]["duration_ms"] == 42


# ── Concurrent: Parallelism limit ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ide_dispatch_respects_parallelism_limit() -> None:
    """TASK-AE2-001: Dispatch returns parallel_limit_exceeded when limit reached."""
    from app.services.conductor import ConductorService

    service = ConductorService()
    dispatch_stub = SimpleNamespace(id=uuid4(), result={}, status="dispatched")
    db = SimpleNamespace(commit=AsyncMock())

    limited_policy = EffectivePolicy(agent_role="worker", max_parallel=1, cooldown_seconds=0)

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch_stub.result = result
        return dispatch_stub

    with patch("app.config.settings.hivemind_conductor_enabled", True), \
         patch("app.services.dispatch_policy.get_effective_policy", AsyncMock(return_value=limited_policy)), \
         patch("app.services.dispatch_policy.count_active_dispatches", AsyncMock(return_value=1)), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_resolve_dispatch_context", AsyncMock(return_value={})), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value={})), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_serialize_thread_context", return_value={}):
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-CONC-001",
            trigger_detail="state:scoped->in_progress",
            agent_role="worker",
            prompt_type="worker_implement",
            db=db,
            execution_mode="ide",
        )

    assert result["status"] == "parallel_limit_exceeded"
    assert result["skip_reason"] == SkipReason.PARALLEL_LIMIT_EXCEEDED


@pytest.mark.asyncio
async def test_ide_dispatch_allows_when_under_limit() -> None:
    """TASK-AE2-001: Dispatch proceeds when under parallelism limit."""
    from app.services.conductor import ConductorService

    service = ConductorService()
    dispatch = _make_dispatch()
    db = SimpleNamespace(commit=AsyncMock())

    open_policy = EffectivePolicy(agent_role="worker", max_parallel=3, cooldown_seconds=0)

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch.result = result or dispatch.result
        return dispatch

    with patch("app.config.settings.hivemind_conductor_enabled", True), \
         patch("app.services.dispatch_policy.get_effective_policy", AsyncMock(return_value=open_policy)), \
         patch("app.services.dispatch_policy.count_active_dispatches", AsyncMock(return_value=1)), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_resolve_dispatch_context", AsyncMock(return_value={})), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value={})), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_serialize_thread_context", return_value={}), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="test prompt")), \
         patch("app.services.event_bus.publish") as mock_publish:
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-CONC-002",
            trigger_detail="state:scoped->in_progress",
            agent_role="worker",
            prompt_type="worker_implement",
            db=db,
            execution_mode="ide",
        )

    assert result["status"] == "ide_dispatched"
    mock_publish.assert_called_once()
