from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.conductor import ManualDispatchRequest, manual_dispatch
from app.services.agentic_dispatch import _filter_tools_for_agent


def test_filter_tools_for_agent_uses_role_specific_tools() -> None:
    tools = [
        {"name": "hivemind-fs_read"},
        {"name": "hivemind-get_task"},
        {"name": "hivemind-submit_result"},
        {"name": "hivemind-propose_skill"},
        {"name": "hivemind-create_wiki_article"},
    ]

    worker_tools = _filter_tools_for_agent(tools, "worker")
    gaertner_tools = _filter_tools_for_agent(tools, "gaertner")

    assert {tool["name"] for tool in worker_tools} == {
        "hivemind-fs_read",
        "hivemind-get_task",
        "hivemind-submit_result",
    }
    assert {tool["name"] for tool in gaertner_tools} == {
        "hivemind-fs_read",
        "hivemind-get_task",
        "hivemind-propose_skill",
        "hivemind-create_wiki_article",
    }


@pytest.mark.asyncio
async def test_manual_dispatch_prefers_generated_prompt_for_task_context() -> None:
    db = AsyncMock()
    provider = object()
    agentic_result = SimpleNamespace(
        error=None,
        content="done",
        tool_calls_executed=[],
        iterations=1,
        total_input_tokens=21,
        total_output_tokens=34,
        model="test-model",
    )

    with patch("app.services.ai_provider.get_provider", AsyncMock(return_value=provider)), \
         patch("app.routers.conductor._resolve_manual_prompt", AsyncMock(return_value=("generated prompt", "generated"))), \
         patch("app.services.agentic_dispatch.agentic_dispatch", AsyncMock(return_value=agentic_result)) as mock_dispatch:
        response = await manual_dispatch(
            body=ManualDispatchRequest(
                agent_role="worker",
                prompt="raw description",
                task_key="TASK-88",
            ),
            db=db,
            current_user=None,
        )

    assert response["status"] == "completed"
    assert response["prompt_source"] == "generated"
    assert mock_dispatch.await_args.kwargs["prompt"] == "generated prompt"
