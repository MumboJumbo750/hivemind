"""Unit tests for IDE conductor dispatch lifecycle (TASK-IDE-005)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.config import settings
from app.routers.conductor import CompleteDispatchRequest, DispatchProgressRequest
from app.services.conductor import ConductorService


def _mock_db_with_dispatch(dispatch) -> AsyncMock:
    db = AsyncMock()
    row = MagicMock()
    row.scalar_one_or_none.return_value = dispatch
    db.execute = AsyncMock(return_value=row)
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_ide_dispatch_publishes_sse_without_provider_lookup() -> None:
    service = ConductorService()
    dispatch = SimpleNamespace(id=uuid4(), result={})
    db = AsyncMock()
    db.commit = AsyncMock()

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(settings, "hivemind_conductor_cooldown_seconds", 10), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_record_dispatch", AsyncMock(return_value=dispatch)), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="full agent prompt")), \
         patch("app.services.event_bus.publish") as mock_publish, \
         patch("app.services.ai_provider.get_provider", new_callable=AsyncMock) as mock_get_provider:
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-IDE-005",
            trigger_detail="state:scoped->in_progress",
            agent_role="worker",
            prompt_type="worker_implement",
            db=db,
            execution_mode="ide",
        )

    assert result["status"] == "ide_dispatched"
    assert result["dispatch_id"] == str(dispatch.id)
    mock_get_provider.assert_not_called()
    mock_publish.assert_called_once()
    event_type, payload = mock_publish.call_args.args[:2]
    assert event_type == "conductor:dispatch"
    assert payload["dispatch_id"] == str(dispatch.id)
    assert payload["execution_mode"] == "ide"
    assert payload["prompt"] == "full agent prompt"


@pytest.mark.asyncio
async def test_rule_execution_mode_can_be_configured_per_rule() -> None:
    service = ConductorService()
    db = AsyncMock()
    row = SimpleNamespace(
        value='{"task_scoped_to_in_progress":{"execution_mode":"ide","fallback_chain":["ide","local","byoai"]}}'
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = row
    db.execute = AsyncMock(return_value=result)

    mode, chain = await service._resolve_rule_dispatch_config(db, "task_scoped_to_in_progress")
    assert mode == "ide"
    assert chain == ["ide", "local", "byoai"]


@pytest.mark.asyncio
async def test_running_and_failed_lifecycle_transitions() -> None:
    from app.routers.conductor import (
        complete_ide_dispatch,
        mark_ide_dispatch_running,
        report_ide_dispatch_progress,
    )

    dispatch_id = str(uuid4())
    dispatch = SimpleNamespace(id=uuid4(), status="acknowledged", result={})
    db = _mock_db_with_dispatch(dispatch)

    running = await mark_ide_dispatch_running(dispatch_id, db=db, current_user=None)
    assert running["status"] == "running"
    assert dispatch.status == "running"
    assert "running_at" in dispatch.result

    failed = await complete_ide_dispatch(
        dispatch_id,
        body=CompleteDispatchRequest(status="failed", result="execution failed"),
        db=db,
        current_user=None,
    )
    assert failed["status"] == "failed"
    assert dispatch.status == "failed"
    assert dispatch.result["error"] == "execution failed"
    assert dispatch.completed_at is not None

    timed_out = await complete_ide_dispatch(
        dispatch_id,
        body=CompleteDispatchRequest(status="timed_out", error="timeout"),
        db=db,
        current_user=None,
    )
    assert timed_out["status"] == "timed_out"
    assert dispatch.status == "timed_out"
    assert dispatch.result["error"] == "timeout"

    cancelled = await complete_ide_dispatch(
        dispatch_id,
        body=CompleteDispatchRequest(status="cancelled", result="user cancelled"),
        db=db,
        current_user=None,
    )
    assert cancelled["status"] == "cancelled"
    assert dispatch.status == "cancelled"
    assert dispatch.result["result"] == "user cancelled"

    progress = await report_ide_dispatch_progress(
        dispatch_id,
        body=DispatchProgressRequest(stage="mcp_call", message="hivemind/submit_result"),
        db=db,
        current_user=None,
    )
    assert progress["status"] in {"running", "cancelled"}
    assert isinstance(dispatch.result.get("progress"), list)
    assert dispatch.result["progress"][-1]["stage"] == "mcp_call"
    assert dispatch.result["progress"][-1]["message"] == "hivemind/submit_result"
    assert "last_progress_at" in dispatch.result


@pytest.mark.asyncio
async def test_ide_timeout_triggers_real_fallback_dispatch() -> None:
    from app.services.conductor_ide_timeout import ide_timeout_job

    now = datetime.now(UTC)
    stale_dispatch = SimpleNamespace(
        id=uuid4(),
        trigger_type="task_state",
        trigger_id="TASK-IDE-005",
        trigger_detail="state:scoped->in_progress",
        agent_role="worker",
        prompt_type="worker_implement",
        execution_mode="ide",
        status="dispatched",
        dispatched_at=now - timedelta(seconds=301),
        completed_at=None,
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

    assert stale_dispatch.status == "timed_out"
    assert stale_dispatch.result["fallback_dispatched"] == "local"
    assert stale_dispatch.completed_at is not None
    mock_dispatch.assert_called_once()
    kwargs = mock_dispatch.call_args.kwargs
    assert kwargs["execution_mode"] == "local"
    assert kwargs["fallback_chain"] == ["local", "byoai"]
