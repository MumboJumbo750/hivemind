from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.routers.conductor import ManualDispatchRequest, manual_dispatch
from app.services.agentic_dispatch import (
    _build_system_prompt,
    _filter_tools_for_agent,
    _parse_text_tool_calls,
)


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


def test_parse_text_tool_calls_logs_on_malformed_json(caplog: pytest.LogCaptureFixture) -> None:
    """TASK-ADI-001: Malformed JSON in <tool_call> blocks is logged at DEBUG level."""
    content = (
        '<tool_call>{"name": "hivemind-get_task", "arguments": {"task_key": "TASK-1"}}</tool_call>'
        "<tool_call>this is not valid json at all</tool_call>"
    )
    import logging
    with caplog.at_level(logging.DEBUG, logger="app.services.agentic_dispatch"):
        result = _parse_text_tool_calls(content)

    # Only the valid tool call should be returned
    assert len(result) == 1
    assert result[0].name == "hivemind-get_task"

    # The malformed entry should have produced a DEBUG log
    debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("parse failed" in msg for msg in debug_messages), (
        f"Expected 'parse failed' in debug logs, got: {debug_messages}"
    )


def test_parse_text_tool_calls_logs_summary(caplog: pytest.LogCaptureFixture) -> None:
    """TASK-ADI-001: Summary log after successful parsing."""
    content = '<tool_call>{"name": "hivemind-get_task", "arguments": {}}</tool_call>'
    import logging
    with caplog.at_level(logging.DEBUG, logger="app.services.agentic_dispatch"):
        result = _parse_text_tool_calls(content)

    assert len(result) == 1
    debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Parsed 1 text tool calls" in msg for msg in debug_messages)


def test_build_system_prompt_truncation_warning_present() -> None:
    """TASK-ADI-003: Truncation notice is included in system prompt when truncation occurs."""
    system = _build_system_prompt(
        "worker",
        truncation_info={"original": 80000, "truncated": 60000},
    )
    assert "WARNUNG" in system
    assert "80,000" in system or "80000" in system
    assert "20,000" in system or "20000" in system
    assert "hivemind-get_task" in system


def test_build_system_prompt_no_truncation_warning_without_info() -> None:
    """TASK-ADI-003: No truncation notice when no truncation occurred."""
    system = _build_system_prompt("worker")
    assert "gekürzt" not in system.lower()
    assert "WARNUNG" not in system or "Prompt wurde gekürzt" not in system


def test_parse_text_tool_calls_filters_unknown_tools(caplog: pytest.LogCaptureFixture) -> None:
    """TASK-ADI-004: Unknown tool names are logged and filtered."""
    content = (
        '<tool_call>{"name": "hivemind-get_task", "arguments": {}}</tool_call>'
        '<tool_call>{"name": "hivemind-hallucinated_tool", "arguments": {}}</tool_call>'
    )
    import logging
    known = {"hivemind-get_task", "hivemind-submit_result"}
    with caplog.at_level(logging.WARNING, logger="app.services.agentic_dispatch"):
        result = _parse_text_tool_calls(content, known_tools=known)

    # Only the known tool should be returned
    assert len(result) == 1
    assert result[0].name == "hivemind-get_task"

    # The unknown tool should have produced a WARNING log
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("hallucinated" in msg for msg in warning_messages)


def test_parse_text_tool_calls_no_filter_without_known_tools() -> None:
    """TASK-ADI-004: Without known_tools, all valid tool calls pass through."""
    content = '<tool_call>{"name": "hivemind-any_tool", "arguments": {}}</tool_call>'
    result = _parse_text_tool_calls(content, known_tools=None)
    assert len(result) == 1
    assert result[0].name == "hivemind-any_tool"


# --- TASK-ADI-002: Circuit Breaker Tests ---

from app.services.ai_provider import CircuitBreaker, CircuitBreakerState


def test_circuit_breaker_closed_to_open() -> None:
    """TASK-ADI-002: CB transitions CLOSED → OPEN after N failures."""
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.allow_request()

    for _ in range(3):
        cb.record_failure()

    assert cb.state == CircuitBreakerState.OPEN
    assert not cb.allow_request()


def test_circuit_breaker_open_to_half_open() -> None:
    """TASK-ADI-002: CB transitions OPEN → HALF_OPEN after recovery timeout."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1000.0)  # long timeout
    cb.record_failure()
    cb.record_failure()
    assert cb._state == CircuitBreakerState.OPEN  # use internal state to avoid auto-transition
    assert not cb.allow_request()

    # Simulate timeout expiry by manipulating last_failure_time
    cb._last_failure_time = time.monotonic() - 1001.0
    assert cb.state == CircuitBreakerState.HALF_OPEN
    assert cb.allow_request()  # probe allowed


def test_circuit_breaker_half_open_success_closes() -> None:
    """TASK-ADI-002: Successful probe in HALF_OPEN → CLOSED."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1000.0)
    cb.record_failure()
    cb.record_failure()
    cb._last_failure_time = time.monotonic() - 1001.0
    assert cb.state == CircuitBreakerState.HALF_OPEN

    cb.record_success()
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb._failure_count == 0


def test_circuit_breaker_half_open_failure_reopens() -> None:
    """TASK-ADI-002: Failed probe in HALF_OPEN → OPEN."""
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1000.0)
    cb.record_failure()
    cb.record_failure()
    cb._last_failure_time = time.monotonic() - 1001.0
    assert cb.state == CircuitBreakerState.HALF_OPEN

    cb.record_failure()
    assert cb._state == CircuitBreakerState.OPEN
