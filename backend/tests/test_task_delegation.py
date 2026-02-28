"""Tests for Task Delegation + ausgehende State-Updates — TASK-F-009."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Outgoing: notify_peer_task_update called on state transition ─────────────

@pytest.mark.asyncio
async def test_transition_state_calls_notify_for_delegated_task():
    """State change on a delegated task creates outbox entry via notify_peer_task_update."""
    from app.services.task_service import TaskService
    from app.schemas.task import TaskStateTransition

    task_id = uuid.uuid4()
    epic_id = uuid.uuid4()
    assigned_node = uuid.uuid4()

    task = MagicMock()
    task.id = task_id
    task.task_key = "TASK-DEL-1"
    task.state = "ready"
    task.qa_failed_count = 0
    task.epic_id = epic_id
    task.assigned_node_id = assigned_node
    task.result = None
    task.version = 1

    epic = MagicMock()
    epic.state = "active"
    epic.version = 1

    db = AsyncMock()

    svc = TaskService(db)

    body = TaskStateTransition(state="in_progress")

    with patch.object(svc, "get_by_key", new_callable=AsyncMock, return_value=task), \
         patch("app.services.task_service._get_epic", new_callable=AsyncMock, return_value=epic), \
         patch("app.services.task_service._all_sibling_states", new_callable=AsyncMock, return_value=["in_progress"]), \
         patch("app.services.federation_service.notify_peer_task_update", new_callable=AsyncMock) as mock_notify:

        await svc.transition_state("TASK-DEL-1", body)

        mock_notify.assert_awaited_once_with(
            db, task_id, "TASK-DEL-1", "in_progress", assigned_node,
            result_text=None,
        )


@pytest.mark.asyncio
async def test_transition_state_skips_notify_without_assigned_node():
    """No outbox entry when task has no assigned_node_id."""
    from app.services.task_service import TaskService
    from app.schemas.task import TaskStateTransition

    task = MagicMock()
    task.id = uuid.uuid4()
    task.task_key = "TASK-LOCAL"
    task.state = "ready"
    task.qa_failed_count = 0
    task.epic_id = uuid.uuid4()
    task.assigned_node_id = None
    task.result = None
    task.version = 1

    epic = MagicMock()
    epic.state = "active"
    epic.version = 1

    db = AsyncMock()
    svc = TaskService(db)
    body = TaskStateTransition(state="in_progress")

    with patch.object(svc, "get_by_key", new_callable=AsyncMock, return_value=task), \
         patch("app.services.task_service._get_epic", new_callable=AsyncMock, return_value=epic), \
         patch("app.services.task_service._all_sibling_states", new_callable=AsyncMock, return_value=["in_progress"]), \
         patch("app.services.federation_service.notify_peer_task_update", new_callable=AsyncMock) as mock_notify:

        await svc.transition_state("TASK-LOCAL", body)

        mock_notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_review_calls_notify_for_delegated_task():
    """Approve review on a delegated task triggers notify."""
    from app.services.task_service import TaskService
    from app.schemas.task import TaskReview

    task_id = uuid.uuid4()
    epic_id = uuid.uuid4()
    assigned_node = uuid.uuid4()

    task = MagicMock()
    task.id = task_id
    task.task_key = "TASK-REV-1"
    task.state = "in_review"
    task.qa_failed_count = 0
    task.epic_id = epic_id
    task.assigned_node_id = assigned_node
    task.result = "completed"
    task.version = 1

    epic = MagicMock()
    epic.state = "active"
    epic.version = 1

    db = AsyncMock()
    svc = TaskService(db)
    body = TaskReview(action="approve")

    with patch.object(svc, "get_by_key", new_callable=AsyncMock, return_value=task), \
         patch("app.services.task_service._get_epic", new_callable=AsyncMock, return_value=epic), \
         patch("app.services.task_service._all_sibling_states", new_callable=AsyncMock, return_value=["done"]), \
         patch("app.services.federation_service.notify_peer_task_update", new_callable=AsyncMock) as mock_notify:

        await svc.review("TASK-REV-1", body)

        mock_notify.assert_awaited_once_with(
            db, task_id, "TASK-REV-1", "done", assigned_node,
            result_text="completed",
        )


# ─── Incoming: origin-authority validation on /federation/task/update ──────────

@pytest.mark.asyncio
async def test_incoming_task_update_rejects_wrong_node():
    """403 when sending node is not the assigned node."""
    from app.routers.federation import task_update
    from app.schemas.federation import FederatedTaskUpdate
    from fastapi import HTTPException

    task = MagicMock()
    task.assigned_node_id = uuid.uuid4()
    task.state = "in_progress"
    task.task_key = "TASK-X"
    task.version = 1

    request = MagicMock()
    request.state.federation_node_id = uuid.uuid4()  # different node

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    db.execute.return_value = r

    body = FederatedTaskUpdate(external_id="TASK-X", state="done")

    with pytest.raises(HTTPException) as exc_info:
        await task_update(body, request, db)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_incoming_task_update_validates_state_machine():
    """422 when requested state transition is invalid."""
    from app.routers.federation import task_update
    from app.schemas.federation import FederatedTaskUpdate
    from fastapi import HTTPException

    assigned_node = uuid.uuid4()
    task = MagicMock()
    task.assigned_node_id = assigned_node
    task.state = "incoming"  # can't go directly to done
    task.task_key = "TASK-Y"
    task.version = 1

    request = MagicMock()
    request.state.federation_node_id = assigned_node

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    db.execute.return_value = r

    body = FederatedTaskUpdate(external_id="TASK-Y", state="done")

    with pytest.raises(HTTPException) as exc_info:
        await task_update(body, request, db)

    assert exc_info.value.status_code == 422
    assert "Invalid transition" in exc_info.value.detail


@pytest.mark.asyncio
async def test_incoming_task_update_valid_transition():
    """Valid incoming task update succeeds."""
    from app.routers.federation import task_update
    from app.schemas.federation import FederatedTaskUpdate

    assigned_node = uuid.uuid4()
    task = MagicMock()
    task.assigned_node_id = assigned_node
    task.state = "ready"
    task.task_key = "TASK-Z"
    task.version = 1
    task.result = None

    request = MagicMock()
    request.state.federation_node_id = assigned_node

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = task
    db.execute.return_value = r

    body = FederatedTaskUpdate(external_id="TASK-Z", state="in_progress")

    result = await task_update(body, request, db)

    assert result.task_key == "TASK-Z"
    assert result.state == "in_progress"
    assert result.updated is True
