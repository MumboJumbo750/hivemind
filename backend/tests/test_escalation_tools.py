"""Unit-Tests für Escalation Tools — Phase 6 MCP tools (TASK-6-005/006/007)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _begin_cm():
    """Async context manager for db.begin()."""
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ── resolve_decision_request tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_dr_success() -> None:
    """resolve_decision_request resolves DR + creates record + transitions task."""
    dr_id = uuid4()
    task_id = uuid4()

    mock_dr = MagicMock()
    mock_dr.id = dr_id
    mock_dr.state = "open"
    mock_dr.epic_id = uuid4()
    mock_dr.task_id = task_id
    mock_dr.version = 0

    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.task_key = "TASK-1-001"
    mock_task.state = "blocked"
    mock_task.version = 0

    call_count = [0]
    async def mock_execute(query, *a, **kw):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = mock_dr
        else:
            result.scalar_one_or_none.return_value = mock_task
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.begin = MagicMock(return_value=_begin_cm())

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.mcp.tools.escalation_tools.AsyncSessionLocal", mock_session_local), \
         patch("app.mcp.tools.escalation_tools.write_audit", new_callable=AsyncMock):
        from app.mcp.tools.escalation_tools import _handle_resolve_decision_request
        result = await _handle_resolve_decision_request({
            "decision_request_id": str(dr_id),
            "decision": "Option A",
            "rationale": "Best choice",
        })

    import json
    data = json.loads(result[0].text)
    assert "error" not in data
    assert data["data"]["state"] == "resolved"
    assert mock_dr.state == "resolved"


@pytest.mark.asyncio
async def test_resolve_dr_not_open_409() -> None:
    """resolve_decision_request on non-open DR returns 409."""
    dr_id = uuid4()
    mock_dr = MagicMock()
    mock_dr.id = dr_id
    mock_dr.state = "resolved"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_dr

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.begin = MagicMock(return_value=_begin_cm())

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.mcp.tools.escalation_tools.AsyncSessionLocal", mock_session_local):
        from app.mcp.tools.escalation_tools import _handle_resolve_decision_request
        result = await _handle_resolve_decision_request({
            "decision_request_id": str(dr_id),
            "decision": "Option A",
        })

    import json
    data = json.loads(result[0].text)
    assert data["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_resolve_dr_empty_decision_422() -> None:
    """resolve_decision_request with empty decision returns 422."""
    from app.mcp.tools.escalation_tools import _handle_resolve_decision_request
    result = await _handle_resolve_decision_request({
        "decision_request_id": str(uuid4()),
        "decision": "",
    })
    import json
    data = json.loads(result[0].text)
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_resolve_dr_uses_actor_id() -> None:
    """resolve_decision_request should use passed actor_id instead of default."""
    from app.mcp.tools.escalation_tools import _resolve_actor

    custom_actor = uuid4()
    result = _resolve_actor({"actor_id": str(custom_actor)})
    assert result == custom_actor


@pytest.mark.asyncio
async def test_resolve_actor_fallback() -> None:
    """_resolve_actor falls back to ADMIN_ID when no actor_id provided."""
    from app.mcp.tools.escalation_tools import _resolve_actor, ADMIN_ID

    result = _resolve_actor({})
    assert result == ADMIN_ID

    result2 = _resolve_actor({"actor_id": "invalid-uuid"})
    assert result2 == ADMIN_ID


# ── resolve_escalation tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_escalation_success() -> None:
    """resolve_escalation: escalated → in_progress, resets qa_failed_count."""
    mock_task = MagicMock()
    mock_task.id = uuid4()
    mock_task.task_key = "TASK-1-001"
    mock_task.title = "Test Task"
    mock_task.state = "escalated"
    mock_task.qa_failed_count = 3
    mock_task.assigned_to = None
    mock_task.version = 5

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.begin = MagicMock(return_value=_begin_cm())

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.mcp.tools.escalation_tools.AsyncSessionLocal", mock_session_local), \
         patch("app.mcp.tools.escalation_tools.write_audit", new_callable=AsyncMock):
        from app.mcp.tools.escalation_tools import _handle_resolve_escalation
        result = await _handle_resolve_escalation({"task_key": "TASK-1-001"})

    import json
    data = json.loads(result[0].text)
    assert data["data"]["new_state"] == "in_progress"
    assert data["data"]["qa_failed_count"] == 0
    assert mock_task.state == "in_progress"
    assert mock_task.qa_failed_count == 0


@pytest.mark.asyncio
async def test_resolve_escalation_wrong_state_409() -> None:
    """resolve_escalation on non-escalated task returns 409."""
    mock_task = MagicMock()
    mock_task.state = "in_progress"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.begin = MagicMock(return_value=_begin_cm())

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.mcp.tools.escalation_tools.AsyncSessionLocal", mock_session_local):
        from app.mcp.tools.escalation_tools import _handle_resolve_escalation
        result = await _handle_resolve_escalation({"task_key": "TASK-1-001"})

    import json
    data = json.loads(result[0].text)
    assert data["error"]["code"] == "CONFLICT"


# ── reassign_epic_owner tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reassign_requires_at_least_one_field() -> None:
    """reassign_epic_owner with neither owner_id nor backup_owner_id returns 422."""
    from app.mcp.tools.escalation_tools import _handle_reassign_epic_owner
    result = await _handle_reassign_epic_owner({"epic_key": "EPIC-1"})

    import json
    data = json.loads(result[0].text)
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_reassign_owner_success() -> None:
    """reassign_epic_owner changes owner_id successfully."""
    new_owner = uuid4()
    mock_epic = MagicMock()
    mock_epic.id = uuid4()
    mock_epic.epic_key = "EPIC-1"
    mock_epic.title = "Test"
    mock_epic.owner_id = uuid4()
    mock_epic.backup_owner_id = None
    mock_epic.version = 2

    mock_user = MagicMock()
    mock_user.id = new_owner

    call_count = [0]
    async def mock_execute(query, *a, **kw):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.scalar_one_or_none.return_value = mock_epic
        elif call_count[0] == 2:
            result.scalar_one_or_none.return_value = new_owner  # user exists
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute
    mock_db.flush = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    mock_db.begin = MagicMock(return_value=_begin_cm())

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.mcp.tools.escalation_tools.AsyncSessionLocal", mock_session_local), \
         patch("app.mcp.tools.escalation_tools.write_audit", new_callable=AsyncMock), \
         patch("app.services.notification_service.create_notification", new_callable=AsyncMock):
        from app.mcp.tools.escalation_tools import _handle_reassign_epic_owner
        result = await _handle_reassign_epic_owner({
            "epic_key": "EPIC-1",
            "owner_id": str(new_owner),
        })

    import json
    data = json.loads(result[0].text)
    assert "error" not in data
    assert mock_epic.owner_id == new_owner
