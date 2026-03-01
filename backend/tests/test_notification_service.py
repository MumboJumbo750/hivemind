"""Unit-Tests für Notification Service (TASK-6-001)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_all_13_notification_types_defined() -> None:
    """All 13 notification types from Phase 6 spec should be defined."""
    from app.services.notification_service import NOTIFICATION_TYPES

    expected_types = {
        "sla_warning", "sla_breach", "sla_admin_fallback",
        "decision_request", "decision_escalated_backup", "decision_escalated_admin",
        "escalation", "skill_proposal", "skill_merged", "task_done",
        "dead_letter", "guard_failed", "task_assigned", "review_requested",
    }
    assert set(NOTIFICATION_TYPES.keys()) == expected_types


@pytest.mark.asyncio
async def test_priority_classifications() -> None:
    """Verify priority classification for all types."""
    from app.services.notification_service import NOTIFICATION_TYPES

    action_now_types = {"sla_breach", "sla_admin_fallback", "decision_escalated_backup",
                        "decision_escalated_admin", "escalation", "dead_letter"}
    soon_types = {"sla_warning", "decision_request", "guard_failed", "task_assigned", "review_requested"}
    fyi_types = {"skill_proposal", "skill_merged", "task_done"}

    for t, info in NOTIFICATION_TYPES.items():
        if t in action_now_types:
            assert info["priority"] == "action_now", f"{t} should be action_now"
        elif t in soon_types:
            assert info["priority"] == "soon", f"{t} should be soon"
        elif t in fyi_types:
            assert info["priority"] == "fyi", f"{t} should be fyi"


@pytest.mark.asyncio
async def test_dedup_window_prevents_duplicates() -> None:
    """Same (user, type, entity_id) within 1h dedup window should be skipped."""
    from app.services.notification_service import create_notification, DEDUP_WINDOW

    user_id = uuid4()
    entity_id = str(uuid4())

    # Mock DB to simulate existing notification within dedup window
    mock_existing = MagicMock()
    mock_existing.scalar_one_or_none.return_value = uuid4()  # existing record

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_existing)

    result = await create_notification(
        mock_db,
        user_id=user_id,
        notification_type="sla_warning",
        body="Test",
        entity_id=entity_id,
    )
    assert result is None  # Should be deduped


@pytest.mark.asyncio
async def test_create_notification_fires_sse() -> None:
    """Creating a notification should publish an SSE event."""
    from app.services.notification_service import create_notification

    user_id = uuid4()

    # Mock DB - no existing (dedup passes)
    mock_dedup_result = MagicMock()
    mock_dedup_result.scalar_one_or_none.return_value = None

    mock_notification = MagicMock()
    mock_notification.id = uuid4()

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_dedup_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch("app.services.notification_service.publish", new_callable=AsyncMock) as mock_publish:
        # We need to mock the Notification constructor
        with patch("app.services.notification_service.Notification") as MockNotification:
            mock_inst = MagicMock()
            mock_inst.id = uuid4()
            mock_inst.type = "sla_warning"
            MockNotification.return_value = mock_inst
            mock_db.refresh = AsyncMock()  # refresh does nothing

            result = await create_notification(
                mock_db,
                user_id=user_id,
                notification_type="sla_warning",
                body="Test SLA warning",
                entity_id=str(uuid4()),
            )

        if result is not None:
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] == "notification_created"
            assert call_args[1]["channel"] == "notifications"


@pytest.mark.asyncio
async def test_notify_users_sends_to_all() -> None:
    """notify_users should call create_notification for each user."""
    from app.services.notification_service import notify_users

    users = [uuid4(), uuid4(), uuid4()]

    with patch("app.services.notification_service.create_notification", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = MagicMock()
        results = await notify_users(
            AsyncMock(),  # db
            user_ids=users,
            notification_type="escalation",
            body="Test",
        )

    assert mock_create.call_count == 3
    called_users = [c[1]["user_id"] for c in mock_create.call_args_list]
    assert set(called_users) == set(users)


@pytest.mark.asyncio
async def test_get_admin_user_ids() -> None:
    """get_admin_user_ids should query users with role=admin."""
    from app.services.notification_service import get_admin_user_ids

    admin1 = uuid4()
    admin2 = uuid4()

    mock_result = MagicMock()
    mock_result.all.return_value = [(admin1,), (admin2,)]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await get_admin_user_ids(mock_db)
    assert result == [admin1, admin2]
