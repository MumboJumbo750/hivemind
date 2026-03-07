from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.schemas.task import TaskStateTransition
from app.services.conductor import ConductorService, _prompt_context_for_dispatch
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
