from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.services.conductor import ConductorService, conductor_poll_job


@pytest.mark.asyncio
async def test_dispatch_records_project_repo_context() -> None:
    dispatch_obj = SimpleNamespace(id=uuid.uuid4(), result={}, status="dispatched", completed_at=None)
    project_id = uuid.uuid4()
    db = SimpleNamespace(commit=AsyncMock())

    svc = ConductorService()
    agentic_result = SimpleNamespace(
        content="triage done",
        tool_calls_executed=[],
        iterations=1,
        total_input_tokens=50,
        total_output_tokens=20,
        model="test-model",
        finish_reason="stop",
        error=None,
    )

    async def fake_update(_db, current_dispatch, *, status, result=None, mark_completed=False):
        current_dispatch.status = status
        if result is not None:
            current_dispatch.result = result
        if mark_completed:
            current_dispatch.completed_at = "done"

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(svc, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(
             svc,
             "_resolve_dispatch_context",
             AsyncMock(
                 return_value={
                     "project_id": str(project_id),
                     "project_slug": "core-api",
                     "workspace_root": "/workspace",
                     "repo_host_path": "C:/repos/core-api",
                 }
             ),
         ), \
         patch.object(svc, "_record_dispatch", AsyncMock(return_value=dispatch_obj)) as record_mock, \
         patch.object(svc, "_update_dispatch", AsyncMock(side_effect=fake_update)), \
         patch.object(svc, "_build_prompt", AsyncMock(return_value="triage prompt")), \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", AsyncMock(return_value=agentic_result)):
        result = await svc.dispatch(
            trigger_type="event",
            trigger_id=str(uuid.uuid4()),
            trigger_detail="event_type:youtrack_issue_update",
            agent_role="triage",
            prompt_type="triage_classify",
            db=db,
        )

    record_payload = record_mock.await_args.kwargs["result"]
    assert record_payload["dispatch_context"]["project_slug"] == "core-api"
    assert record_payload["dispatch_context"]["repo_host_path"] == "C:/repos/core-api"
    assert result["execution_mode"] == "local"


@pytest.mark.asyncio
async def test_on_inbound_event_marks_dispatch_status_and_skips_repeat() -> None:
    event_id = uuid.uuid4()
    entry = SimpleNamespace(
        id=event_id,
        routing_detail={"intake_stage": "triage_pending"},
        routing_state="unrouted",
    )
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = entry
    db = AsyncMock()
    db.execute.return_value = scalar_result

    svc = ConductorService()
    dispatch_mock = AsyncMock(return_value={"status": "ide_dispatched", "dispatch_id": "disp-1", "execution_mode": "ide"})

    with patch.object(svc, "_resolve_rule_dispatch_config", AsyncMock(return_value=("ide", ["ide", "local", "byoai"]))), \
         patch.object(svc, "dispatch", dispatch_mock):
        await svc.on_inbound_event(str(event_id), "youtrack_issue_update", db)
        await svc.on_inbound_event(str(event_id), "youtrack_issue_update", db)

    dispatch_mock.assert_awaited_once()
    assert entry.routing_detail["dispatch_status"] == "ide_dispatched"
    assert entry.routing_detail["dispatch_mode"] == "ide"


@pytest.mark.asyncio
async def test_conductor_poll_job_only_dispatches_triage_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    triage_pending = SimpleNamespace(
        id=uuid.uuid4(),
        direction="inbound",
        routing_state="unrouted",
        entity_type="youtrack_issue_update",
        routing_detail={"intake_stage": "triage_pending"},
    )
    routed_bug = SimpleNamespace(
        id=uuid.uuid4(),
        direction="inbound",
        routing_state="unrouted",
        entity_type="sentry_error",
        routing_detail={"intake_stage": "materialized"},
    )

    result = MagicMock()
    result.scalars.return_value.all.return_value = [triage_pending, routed_bug]
    db = AsyncMock()
    db.execute.return_value = result
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr(settings, "hivemind_conductor_enabled", True)

    with patch("app.db.AsyncSessionLocal", return_value=db), \
         patch("app.services.conductor.conductor.on_inbound_event", AsyncMock()) as on_event:
        await conductor_poll_job()

    on_event.assert_awaited_once_with(
        event_id=str(triage_pending.id),
        event_type="youtrack_issue_update",
        db=db,
    )
