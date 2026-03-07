from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent_threading import (
    AgentThreadService,
    THREAD_POLICY_ATTEMPT,
    THREAD_POLICY_STATELESS,
)


@pytest.mark.asyncio
async def test_resolve_context_uses_attempt_policy_for_worker() -> None:
    service = AgentThreadService(AsyncMock())
    task = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-1",
        version=3,
        qa_failed_count=1,
        epic_id=uuid.uuid4(),
    )
    epic = SimpleNamespace(id=uuid.uuid4(), epic_key="EPIC-1", project_id=uuid.uuid4())
    project = SimpleNamespace(id=uuid.uuid4(), slug="core-api", agent_thread_overrides={})

    with patch.object(service, "_load_provider_thread_policy", AsyncMock(return_value=None)), \
         patch.object(service, "_load_task", AsyncMock(return_value=task)), \
         patch.object(service, "_resolve_epic", AsyncMock(return_value=epic)), \
         patch.object(service, "_resolve_project", AsyncMock(return_value=project)), \
         patch.object(service, "_get_session_by_key", AsyncMock(return_value=None)):
        context = await service.resolve_context(
            agent_role="worker",
            task_id="TASK-1",
            create_session=False,
        )

    assert context["policy"] == THREAD_POLICY_ATTEMPT
    assert context["thread_key"] == "worker:attempt:TASK-1:v3:qa1"
    assert context["reuse_enabled"] is True
    assert "Resume-Regel" in context["prompt_block"]


@pytest.mark.asyncio
async def test_project_override_can_force_stateless() -> None:
    service = AgentThreadService(AsyncMock())
    task = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-2",
        version=1,
        qa_failed_count=0,
        epic_id=uuid.uuid4(),
    )
    epic = SimpleNamespace(id=uuid.uuid4(), epic_key="EPIC-2", project_id=uuid.uuid4())
    project = SimpleNamespace(
        id=uuid.uuid4(),
        slug="frontend",
        agent_thread_overrides={"architekt": "stateless"},
    )

    with patch.object(service, "_load_provider_thread_policy", AsyncMock(return_value="epic_stateful")), \
         patch.object(service, "_load_task", AsyncMock(return_value=task)), \
         patch.object(service, "_resolve_epic", AsyncMock(return_value=epic)), \
         patch.object(service, "_resolve_project", AsyncMock(return_value=project)):
        context = await service.resolve_context(
            agent_role="architekt",
            task_id="TASK-2",
            create_session=False,
        )

    assert context["policy"] == THREAD_POLICY_STATELESS
    assert context["project_override_policy"] == THREAD_POLICY_STATELESS
    assert context["thread_key"] is None


@pytest.mark.asyncio
async def test_record_dispatch_outcome_updates_session_history() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    service = AgentThreadService(db)
    session = SimpleNamespace(
        id=uuid.uuid4(),
        session_metadata={"history": []},
        dispatch_count=0,
        last_activity_at=None,
        summary=None,
    )

    with patch.object(service, "_get_session_by_key", AsyncMock(return_value=session)):
        await service.record_dispatch_outcome(
            thread_context={"thread_key": "worker:attempt:TASK-1:v1:qa0"},
            dispatch_id=str(uuid.uuid4()),
            prompt_type="worker_implement",
            trigger_detail="state:ready->in_progress",
            status="completed",
            content="Implemented the endpoint and updated the tests.",
            model="gpt-4o",
            tool_calls=[{"tool": "hivemind-submit_result"}],
        )

    assert session.dispatch_count == 1
    assert len(session.session_metadata["history"]) == 1
    assert "Implemented the endpoint" in session.summary


@pytest.mark.asyncio
async def test_record_dispatch_outcome_swallows_noncritical_db_errors() -> None:
    service = AgentThreadService(AsyncMock())

    with patch.object(service, "_get_session_by_key", AsyncMock(side_effect=RuntimeError("db closed"))):
        await service.record_dispatch_outcome(
            thread_context={"thread_key": "reviewer:attempt:TASK-2:v1:qa0"},
            dispatch_id=str(uuid.uuid4()),
            prompt_type="reviewer_check",
            trigger_detail="state:in_progress->in_review",
            status="failed",
        )
