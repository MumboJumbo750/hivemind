from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.schemas.task import TaskStateTransition
from app.services.conductor import ConductorService, _is_transient_error, _prompt_context_for_dispatch
from app.services.task_service import TaskService


def test_prompt_context_for_dispatch_maps_supported_entities() -> None:
    assert _prompt_context_for_dispatch(
        trigger_type="task_state",
        trigger_id="TASK-88",
        trigger_detail="state:in_progress->in_review",
        agent_role="reviewer",
        prompt_type="reviewer_check",
    ) == {"task_id": "TASK-88"}

    assert _prompt_context_for_dispatch(
        trigger_type="epic_state",
        trigger_id="EPIC-12",
        trigger_detail="state:incoming->scoped",
        agent_role="architekt",
        prompt_type="architekt_decompose",
    ) == {"epic_id": "EPIC-12"}

    assert _prompt_context_for_dispatch(
        trigger_type="event",
        trigger_id="00000000-0000-0000-0000-000000000123",
        trigger_detail="project:created",
        agent_role="stratege",
        prompt_type="stratege_plan",
    ) == {"project_id": "00000000-0000-0000-0000-000000000123"}

    assert _prompt_context_for_dispatch(
        trigger_type="event",
        trigger_id="SKILL-7",
        trigger_detail="skill:proposal",
        agent_role="triage",
        prompt_type="triage_skill_proposal",
    ) == {"skill_id": "SKILL-7"}

    assert _prompt_context_for_dispatch(
        trigger_type="event",
        trigger_id="GUARD-3",
        trigger_detail="guard:proposal",
        agent_role="triage",
        prompt_type="triage_guard_proposal",
    ) == {"guard_id": "GUARD-3"}

    assert _prompt_context_for_dispatch(
        trigger_type="event",
        trigger_id="00000000-0000-0000-0000-000000000321",
        trigger_detail="decision_request:open",
        agent_role="triage",
        prompt_type="triage_decision_request",
    ) == {"decision_id": "00000000-0000-0000-0000-000000000321"}


@pytest.mark.asyncio
async def test_conductor_local_dispatch_uses_agentic_loop() -> None:
    service = ConductorService()
    dispatch = SimpleNamespace(
        id=uuid.uuid4(),
        result={"fallback_chain": ["local", "byoai"]},
        status="dispatched",
        completed_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock())
    agentic_result = SimpleNamespace(
        content="review completed",
        tool_calls_executed=[{"tool": "hivemind-get_task", "arguments": {"task_key": "TASK-1"}}],
        iterations=2,
        total_input_tokens=120,
        total_output_tokens=45,
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

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch.result = result
        return dispatch

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_update_dispatch", AsyncMock(side_effect=fake_update)), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="generated prompt")), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value={
             "policy": "attempt_stateful",
             "configured_policy": "attempt_stateful",
             "project_override_policy": None,
             "thread_key": "reviewer:attempt:TASK-1:v1:qa0",
             "scope": "attempt:TASK-1 v1 / qa#0",
             "reuse_enabled": True,
             "session_id": str(uuid.uuid4()),
             "prompt_block": "## Thread-Policy",
         })), \
         patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()) as record_thread, \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", AsyncMock(return_value=agentic_result)) as mock_agentic:
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-1",
            trigger_detail="state:in_progress->in_review",
            agent_role="reviewer",
            prompt_type="reviewer_check",
            db=db,
            execution_mode="local",
        )

    assert result["status"] == "completed"
    assert dispatch.status == "completed"
    assert dispatch.result["content"] == "review completed"
    assert dispatch.result["tool_calls"] == agentic_result.tool_calls_executed
    assert dispatch.result["thread_context"]["thread_key"] == "reviewer:attempt:TASK-1:v1:qa0"
    assert result["thread_context"]["policy"] == "attempt_stateful"
    assert mock_agentic.await_args.kwargs["task_key"] == "TASK-1"
    assert mock_agentic.await_args.kwargs["agent_role"] == "reviewer"
    record_thread.assert_awaited()


@pytest.mark.asyncio
async def test_task_service_transition_state_triggers_conductor_hook() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    service = TaskService(db)
    task = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-42",
        state="in_progress",
        qa_failed_count=0,
        version=1,
        assigned_node_id=None,
        result="done",
        epic_id=uuid.uuid4(),
    )
    epic = SimpleNamespace(state="scoped", version=1)

    service.get_by_key = AsyncMock(return_value=task)
    service._trigger_conductor_task_state_change = AsyncMock()

    with patch("app.services.task_service._get_epic", AsyncMock(return_value=epic)), \
         patch("app.services.task_service._all_sibling_states", AsyncMock(return_value=["in_review"])), \
         patch("app.services.task_service.calculate_epic_state_after_task_transition", return_value=None):
        updated = await service.transition_state(
            "TASK-42",
            TaskStateTransition(state="in_review"),
        )

    assert updated.state == "in_review"
    service._trigger_conductor_task_state_change.assert_awaited_once_with(
        task,
        "in_progress",
        "in_review",
    )


@pytest.mark.asyncio
async def test_conductor_dispatches_gaertner_on_qa_failed() -> None:
    service = ConductorService()
    db = AsyncMock()

    with patch.object(service, "_resolve_rule_dispatch_config", AsyncMock(return_value=("local", ["local", "byoai"]))), \
         patch.object(service, "dispatch", AsyncMock()) as dispatch:
        await service.on_task_state_change("TASK-9", "ignored", "in_review", "qa_failed", db)

    dispatch.assert_awaited_once_with(
        trigger_type="task_state",
        trigger_id="TASK-9",
        trigger_detail="state:in_review->qa_failed",
        agent_role="gaertner",
        prompt_type="gaertner_review_feedback",
        db=db,
        execution_mode="local",
        fallback_chain=["local", "byoai"],
    )


@pytest.mark.asyncio
async def test_conductor_dispatches_worker_on_ready_to_in_progress() -> None:
    service = ConductorService()
    db = AsyncMock()

    with patch.object(service, "_resolve_rule_dispatch_config", AsyncMock(return_value=("local", ["local", "byoai"]))), \
         patch.object(service, "dispatch", AsyncMock()) as dispatch:
        await service.on_task_state_change("TASK-READY", "ignored", "ready", "in_progress", db)

    dispatch.assert_awaited_once_with(
        trigger_type="task_state",
        trigger_id="TASK-READY",
        trigger_detail="state:ready->in_progress",
        agent_role="worker",
        prompt_type="worker_implement",
        db=db,
        execution_mode="local",
        fallback_chain=["local", "byoai"],
    )


@pytest.mark.asyncio
async def test_conductor_dispatches_worker_on_qa_failed_reentry() -> None:
    service = ConductorService()
    db = AsyncMock()

    with patch.object(service, "_resolve_rule_dispatch_config", AsyncMock(return_value=("local", ["local", "byoai"]))), \
         patch.object(service, "dispatch", AsyncMock()) as dispatch:
        await service.on_task_state_change("TASK-RETRY", "ignored", "qa_failed", "in_progress", db)

    dispatch.assert_awaited_once_with(
        trigger_type="task_state",
        trigger_id="TASK-RETRY",
        trigger_detail="state:qa_failed->in_progress",
        agent_role="worker",
        prompt_type="worker_implement",
        db=db,
        execution_mode="local",
        fallback_chain=["local", "byoai"],
    )


@pytest.mark.asyncio
async def test_task_service_reenter_triggers_conductor_hook() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(
        return_value=SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
    )

    service = TaskService(db)
    task = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-REENTER",
        state="qa_failed",
        qa_failed_count=1,
        version=4,
        assigned_node_id=None,
        result="retry",
        epic_id=uuid.uuid4(),
    )
    service.get_by_key = AsyncMock(return_value=task)
    service._trigger_conductor_task_state_change = AsyncMock()

    updated = await service.reenter_from_qa_failed("TASK-REENTER")

    assert updated.state == "in_progress"
    service._trigger_conductor_task_state_change.assert_awaited_once_with(
        task,
        "qa_failed",
        "in_progress",
    )


@pytest.mark.asyncio
async def test_conductor_routes_skill_and_guard_proposals_to_triage() -> None:
    service = ConductorService()
    db = AsyncMock()

    with patch("app.services.governance.get_governance_level", AsyncMock(return_value="auto")), \
         patch.object(service, "_resolve_rule_dispatch_config", AsyncMock(return_value=("local", ["local", "byoai"]))), \
         patch.object(service, "dispatch", AsyncMock()) as dispatch:
        await service.on_skill_proposal("SKILL-7", db)
        await service.on_guard_proposal("GUARD-3", db)

    assert dispatch.await_count == 2
    assert dispatch.await_args_list[0].kwargs == {
        "trigger_type": "event",
        "trigger_id": "SKILL-7",
        "trigger_detail": "skill:proposal",
        "agent_role": "triage",
        "prompt_type": "triage_skill_proposal",
        "db": db,
        "execution_mode": "local",
        "fallback_chain": ["local", "byoai"],
    }
    assert dispatch.await_args_list[1].kwargs == {
        "trigger_type": "event",
        "trigger_id": "GUARD-3",
        "trigger_detail": "guard:proposal",
        "agent_role": "triage",
        "prompt_type": "triage_guard_proposal",
        "db": db,
        "execution_mode": "local",
        "fallback_chain": ["local", "byoai"],
    }


@pytest.mark.asyncio
async def test_conductor_routes_epic_restructure_and_decisions_to_triage() -> None:
    service = ConductorService()
    db = AsyncMock()

    with patch("app.services.governance.get_governance_level", AsyncMock(return_value="assisted")), \
         patch.object(service, "_resolve_rule_dispatch_config", AsyncMock(return_value=("local", ["local", "byoai"]))), \
         patch.object(service, "dispatch", AsyncMock()) as dispatch:
        await service.on_epic_restructure_proposed("00000000-0000-0000-0000-000000000111", db)
        await service.on_decision_request("00000000-0000-0000-0000-000000000222", db)

    assert dispatch.await_count == 2
    assert dispatch.await_args_list[0].kwargs == {
        "trigger_type": "event",
        "trigger_id": "00000000-0000-0000-0000-000000000111",
        "trigger_detail": "epic_restructure:proposed",
        "agent_role": "triage",
        "prompt_type": "triage_epic_restructure",
        "db": db,
        "execution_mode": "local",
        "fallback_chain": ["local", "byoai"],
    }
    assert dispatch.await_args_list[1].kwargs == {
        "trigger_type": "event",
        "trigger_id": "00000000-0000-0000-0000-000000000222",
        "trigger_detail": "decision_request:open",
        "agent_role": "triage",
        "prompt_type": "triage_decision_request",
        "db": db,
        "execution_mode": "local",
        "fallback_chain": ["local", "byoai"],
    }


@pytest.mark.asyncio
async def test_assisted_governance_blocks_decisive_tools_and_persists_recommendation() -> None:
    service = ConductorService()
    dispatch = SimpleNamespace(
        id=uuid.uuid4(),
        result={"fallback_chain": ["local", "byoai"]},
        status="dispatched",
        completed_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock())
    agentic_result = SimpleNamespace(
        content="Recommend accept after dependency review.",
        tool_calls_executed=[],
        iterations=1,
        total_input_tokens=80,
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

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch.result = result
        return dispatch

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_update_dispatch", AsyncMock(side_effect=fake_update)), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="generated prompt")), \
         patch.object(service, "_resolve_dispatch_context", AsyncMock(return_value={"project_id": str(uuid.uuid4())})), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value={
             "policy": "project_stateful",
             "configured_policy": "project_stateful",
             "project_override_policy": None,
             "thread_key": "triage:project:core-api",
             "scope": "project:core-api",
             "reuse_enabled": True,
             "session_id": str(uuid.uuid4()),
             "prompt_block": "## Thread-Policy",
         })), \
         patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()), \
         patch("app.services.governance.get_governance_level", AsyncMock(return_value="assisted")), \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", AsyncMock(return_value=agentic_result)) as mock_agentic, \
         patch("app.services.governance_recommendations.store_governance_recommendation", AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))) as store_rec, \
         patch("app.services.learning_artifacts.capture_dispatch_learning", AsyncMock()), \
         patch("app.services.learning_artifacts.create_learning_artifact", AsyncMock()):
        result = await service.dispatch(
            trigger_type="event",
            trigger_id="proposal-1",
            trigger_detail="epic_proposal:submitted",
            agent_role="triage",
            prompt_type="triage_epic_proposal",
            db=db,
            execution_mode="local",
        )

    assert result["status"] == "completed"
    allowed_tools = mock_agentic.await_args.kwargs["allowed_tool_names"]
    assert "hivemind-accept_epic_proposal" not in allowed_tools
    assert "hivemind-reject_epic_proposal" not in allowed_tools
    assert store_rec.await_count == 1
    assert dispatch.result["governance"]["human_confirmation_required"] is True
    assert "recommendation_id" in dispatch.result["governance"]


@pytest.mark.asyncio
async def test_auto_governance_allows_decisive_tools_without_recommendation_fallback() -> None:
    service = ConductorService()
    dispatch = SimpleNamespace(
        id=uuid.uuid4(),
        result={"fallback_chain": ["local", "byoai"]},
        status="dispatched",
        completed_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock())
    agentic_result = SimpleNamespace(
        content="Accepted.",
        tool_calls_executed=[{"tool": "hivemind-accept_epic_proposal", "arguments": {"proposal_id": "proposal-2"}}],
        iterations=1,
        total_input_tokens=80,
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

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch.result = result
        return dispatch

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_update_dispatch", AsyncMock(side_effect=fake_update)), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="generated prompt")), \
         patch.object(service, "_resolve_dispatch_context", AsyncMock(return_value={"project_id": str(uuid.uuid4())})), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value={
             "policy": "project_stateful",
             "configured_policy": "project_stateful",
             "project_override_policy": None,
             "thread_key": "triage:project:core-api",
             "scope": "project:core-api",
             "reuse_enabled": True,
             "session_id": str(uuid.uuid4()),
             "prompt_block": "## Thread-Policy",
         })), \
         patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()), \
         patch("app.services.governance.get_governance_level", AsyncMock(return_value="auto")), \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", AsyncMock(return_value=agentic_result)) as mock_agentic, \
         patch("app.services.governance_recommendations.store_governance_recommendation", AsyncMock()) as store_rec, \
         patch("app.services.learning_artifacts.capture_dispatch_learning", AsyncMock()), \
         patch("app.services.learning_artifacts.create_learning_artifact", AsyncMock()):
        result = await service.dispatch(
            trigger_type="event",
            trigger_id="proposal-2",
            trigger_detail="epic_proposal:submitted",
            agent_role="triage",
            prompt_type="triage_epic_proposal",
            db=db,
            execution_mode="local",
        )

    assert result["status"] == "completed"
    assert mock_agentic.await_args.kwargs["allowed_tool_names"] is None
    assert store_rec.await_count == 0
    assert dispatch.result["governance"]["decisive_tool_called"] is True


@pytest.mark.asyncio
async def test_conductor_dispatches_triage_on_escalated_when_governed() -> None:
    service = ConductorService()
    db = AsyncMock()

    with patch("app.services.governance.get_governance_level", AsyncMock(return_value="auto")), \
         patch.object(service, "_resolve_rule_dispatch_config", AsyncMock(return_value=("local", ["local", "byoai"]))), \
         patch.object(service, "dispatch", AsyncMock()) as dispatch:
        await service.on_task_state_change("TASK-77", "ignored", "qa_failed", "escalated", db)

    dispatch.assert_awaited_once_with(
        trigger_type="task_state",
        trigger_id="TASK-77",
        trigger_detail="state:qa_failed->escalated",
        agent_role="triage",
        prompt_type="triage_escalation",
        db=db,
        execution_mode="local",
        fallback_chain=["local", "byoai"],
    )


# ---------------------------------------------------------------------------
# Transient-Error Retry Tests (TASK-41)
# ---------------------------------------------------------------------------

def test_is_transient_error_classifies_correctly() -> None:
    assert _is_transient_error(asyncio.TimeoutError())
    assert _is_transient_error(TimeoutError())
    assert _is_transient_error(ConnectionError("refused"))
    assert not _is_transient_error(ValueError("bad input"))
    assert not _is_transient_error(RuntimeError("auth failed"))
    assert not _is_transient_error(Exception("generic"))


def _make_dispatch_fixtures():
    """Return (service, dispatch, db, agentic_result, fake_update, fake_record) tuple."""
    service = ConductorService()
    dispatch = SimpleNamespace(
        id=uuid.uuid4(),
        result={"fallback_chain": ["local", "byoai"]},
        status="dispatched",
        completed_at=None,
    )
    db = SimpleNamespace(commit=AsyncMock())
    agentic_result = SimpleNamespace(
        content="worker output",
        tool_calls_executed=[],
        iterations=1,
        total_input_tokens=40,
        total_output_tokens=15,
        model="test-model",
        finish_reason="stop",
        error=None,
    )
    _thread_ctx = {
        "policy": "attempt_stateful",
        "configured_policy": "attempt_stateful",
        "project_override_policy": None,
        "thread_key": "worker:attempt:TASK-41:v1:qa0",
        "scope": "attempt:TASK-41 v1 / qa#0",
        "reuse_enabled": True,
        "session_id": str(uuid.uuid4()),
        "prompt_block": "## Thread-Policy",
    }

    async def fake_update(_db, current_dispatch, *, status, result=None, mark_completed=False):
        current_dispatch.status = status
        if result is not None:
            current_dispatch.result = result
        if mark_completed:
            current_dispatch.completed_at = "done"

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch.result = result
        return dispatch

    return service, dispatch, db, agentic_result, fake_update, fake_record, _thread_ctx


@pytest.mark.asyncio
async def test_local_dispatch_timeout_retry_succeeds() -> None:
    """TimeoutError on first agentic_dispatch call → retry after 2 s → success."""
    service, dispatch, db, agentic_result, fake_update, fake_record, thread_ctx = (
        _make_dispatch_fixtures()
    )

    agentic_mock = AsyncMock(side_effect=[asyncio.TimeoutError("connect timeout"), agentic_result])
    update_mock = AsyncMock(side_effect=fake_update)

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_update_dispatch", update_mock), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="prompt")), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value=thread_ctx)), \
         patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()), \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", agentic_mock), \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-41",
            trigger_detail="state:ready->in_progress",
            agent_role="worker",
            prompt_type="worker_implement",
            db=db,
            execution_mode="local",
        )

    # dispatch completed successfully on retry
    assert result["status"] == "completed"
    assert dispatch.result["content"] == "worker output"
    # agentic_dispatch called exactly twice (first attempt + one retry)
    assert agentic_mock.await_count == 2
    # asyncio.sleep called once with 2 s backoff
    mock_sleep.assert_awaited_once_with(2)
    # retry info was persisted in an intermediate dispatch update
    update_calls = update_mock.await_args_list
    retry_updates = [
        c for c in update_calls
        if isinstance(c.kwargs.get("result"), dict)
        and c.kwargs["result"].get("retry_attempt") == 1
    ]
    assert retry_updates, "retry_attempt=1 should be recorded in an intermediate dispatch update"
    assert retry_updates[0].kwargs["result"]["retry_error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_local_dispatch_permanent_error_no_retry() -> None:
    """Permanent error (ValueError) goes directly to BYOAI fallback without retry."""
    service, dispatch, db, _agentic_result, fake_update, fake_record, thread_ctx = (
        _make_dispatch_fixtures()
    )

    agentic_mock = AsyncMock(side_effect=ValueError("invalid model config"))

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_update_dispatch", AsyncMock(side_effect=fake_update)), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="prompt")), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value=thread_ctx)), \
         patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()), \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", agentic_mock), \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-41",
            trigger_detail="state:ready->in_progress",
            agent_role="worker",
            prompt_type="worker_implement",
            db=db,
            execution_mode="local",
        )

    # permanent error → BYOAI fallback, no retry
    assert result["status"] == "byoai"
    assert dispatch.result.get("byoai") is True
    assert "invalid model config" in dispatch.result.get("local_error", "")
    # no sleep — permanent error bypasses retry
    mock_sleep.assert_not_awaited()
    # agentic_dispatch called only once
    assert agentic_mock.await_count == 1
    # retry_attempted must NOT be set
    assert not dispatch.result.get("retry_attempted")


@pytest.mark.asyncio
async def test_local_dispatch_transient_error_twice_falls_back_to_byoai() -> None:
    """Two consecutive TimeoutErrors exhaust retries → BYOAI with retry_attempted=True."""
    service, dispatch, db, _agentic_result, fake_update, fake_record, thread_ctx = (
        _make_dispatch_fixtures()
    )

    agentic_mock = AsyncMock(
        side_effect=[asyncio.TimeoutError("first"), asyncio.TimeoutError("second")]
    )

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_update_dispatch", AsyncMock(side_effect=fake_update)), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="prompt")), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value=thread_ctx)), \
         patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()), \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", agentic_mock), \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-41",
            trigger_detail="state:ready->in_progress",
            agent_role="worker",
            prompt_type="worker_implement",
            db=db,
            execution_mode="local",
        )

    # second transient failure → BYOAI fallback
    assert result["status"] == "byoai"
    assert dispatch.result.get("byoai") is True
    # retry was attempted and documented
    assert dispatch.result.get("retry_attempted") is True
    assert "first" in dispatch.result.get("retry_first_error", "")
    # sleep was called once (between attempt 1 and attempt 2)
    mock_sleep.assert_awaited_once_with(2)
    # agentic_dispatch called exactly twice
    assert agentic_mock.await_count == 2


@pytest.mark.asyncio
async def test_expire_stale_non_ide_dispatched_marks_old_local_dispatches_timed_out() -> None:
    service = ConductorService()
    stale_dispatch = SimpleNamespace(
        id=uuid.uuid4(),
        agent_role="worker",
        execution_mode="local",
        status="dispatched",
        completed_at=None,
        dispatched_at=datetime.now(UTC) - timedelta(seconds=601),
        result={"fallback_chain": ["local", "byoai"]},
    )
    row = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [stale_dispatch]))
    db = SimpleNamespace(execute=AsyncMock(return_value=row), flush=AsyncMock())

    expired = await service._expire_stale_non_ide_dispatched(
        db,
        agent_role="worker",
        timeout_seconds=300,
    )

    assert expired == 1
    assert stale_dispatch.status == "timed_out"
    assert stale_dispatch.completed_at is not None
    assert stale_dispatch.result["stale_dispatch_expired"] is True
    assert stale_dispatch.result["timeout_seconds"] == 300
    assert stale_dispatch.result["status_history"][-1]["status"] == "timed_out"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_dispatch_expires_stale_non_ide_before_parallel_gate() -> None:
    service = ConductorService()
    dispatch = SimpleNamespace(id=uuid.uuid4(), result={}, status="dispatched", completed_at=None)
    db = SimpleNamespace(commit=AsyncMock())

    async def fake_record(*_args, result=None, **_kwargs):
        dispatch.result = result
        return dispatch

    async def fake_update(_db, current_dispatch, *, status, result=None, mark_completed=False):
        current_dispatch.status = status
        if result is not None:
            current_dispatch.result = result
        if mark_completed:
            current_dispatch.completed_at = "done"

    with patch.object(settings, "hivemind_conductor_enabled", True), \
         patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
         patch.object(service, "_resolve_dispatch_context", AsyncMock(return_value={})), \
         patch("app.services.agent_threading.AgentThreadService.resolve_context", AsyncMock(return_value={})), \
         patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()), \
         patch.object(service, "_record_dispatch", AsyncMock(side_effect=fake_record)), \
         patch.object(service, "_update_dispatch", AsyncMock(side_effect=fake_update)), \
         patch.object(service, "_build_prompt", AsyncMock(return_value="prompt")), \
         patch.object(service, "_expire_stale_non_ide_dispatched", AsyncMock(return_value=2)) as expire_mock, \
         patch("app.services.dispatch_policy.count_active_dispatches", AsyncMock(return_value=0)) as count_mock, \
         patch("app.services.ai_provider.get_provider", AsyncMock(return_value=object())), \
         patch("app.services.agentic_dispatch.agentic_dispatch", AsyncMock(return_value=SimpleNamespace(
             content="ok",
             tool_calls_executed=[],
             iterations=1,
             total_input_tokens=1,
             total_output_tokens=1,
             model="stub",
             finish_reason="stop",
             error=None,
         ))):
        result = await service.dispatch(
            trigger_type="task_state",
            trigger_id="TASK-77",
            trigger_detail="state:ready->in_progress",
            agent_role="worker",
            prompt_type="worker_implement",
            db=db,
            execution_mode="local",
        )

    assert result["status"] == "completed"
    expire_mock.assert_awaited_once()
    count_mock.assert_awaited_once()
    assert db.commit.await_count >= 3
