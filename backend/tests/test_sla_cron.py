"""Unit-Tests für SLA Cron Job (TASK-6-002)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _make_epic(
    *,
    state="in_progress",
    sla_due_at=None,
    owner_id=None,
    backup_owner_id=None,
):
    epic = MagicMock()
    epic.id = uuid4()
    epic.epic_key = "EPIC-TEST-1"
    epic.title = "Test Epic"
    epic.state = state
    epic.sla_due_at = sla_due_at
    epic.owner_id = owner_id
    epic.backup_owner_id = backup_owner_id
    return epic


def _mock_db(execute_return=None):
    """Build a mock async session with working begin() context manager."""
    mock_db = AsyncMock()
    if execute_return is not None:
        mock_db.execute.return_value = execute_return
    # async with AsyncSessionLocal() as db:
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    # async with db.begin():  — begin() must return sync CM, not coroutine
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    mock_db.begin = MagicMock(return_value=begin_cm)
    return mock_db


@pytest.mark.asyncio
async def test_sla_warning_4h_before() -> None:
    """4h before SLA → sla_warning to epic owner."""
    owner_id = uuid4()
    sla = datetime.now(timezone.utc) + timedelta(hours=3)  # within 4h window
    epic = _make_epic(sla_due_at=sla, owner_id=owner_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [epic]

    db = _mock_db(mock_result)
    mock_session_local = MagicMock(return_value=db)

    with patch("app.services.sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.sla_cron.create_notification", new_callable=AsyncMock) as mock_notify:
        from app.services.sla_cron import sla_cron_job
        await sla_cron_job()

    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args[1]
    assert call_kwargs["user_id"] == owner_id
    assert call_kwargs["notification_type"] == "sla_warning"


@pytest.mark.asyncio
async def test_sla_breach_backup_owner() -> None:
    """SLA breached → sla_breach to backup_owner."""
    backup_id = uuid4()
    sla = datetime.now(timezone.utc) - timedelta(hours=2)  # breached 2h ago
    epic = _make_epic(sla_due_at=sla, owner_id=uuid4(), backup_owner_id=backup_id)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [epic]

    db = _mock_db(mock_result)
    mock_session_local = MagicMock(return_value=db)

    with patch("app.services.sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.sla_cron.create_notification", new_callable=AsyncMock) as mock_notify:
        from app.services.sla_cron import sla_cron_job
        await sla_cron_job()

    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args[1]
    assert call_kwargs["user_id"] == backup_id
    assert call_kwargs["notification_type"] == "sla_breach"


@pytest.mark.asyncio
async def test_sla_breach_no_backup_falls_to_admins() -> None:
    """SLA breached + no backup_owner → notify admins directly."""
    sla = datetime.now(timezone.utc) - timedelta(hours=2)
    epic = _make_epic(sla_due_at=sla, owner_id=uuid4(), backup_owner_id=None)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [epic]

    admin_ids = [uuid4(), uuid4()]
    db = _mock_db(mock_result)
    mock_session_local = MagicMock(return_value=db)

    with patch("app.services.sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.sla_cron.create_notification", new_callable=AsyncMock), \
         patch("app.services.sla_cron.get_admin_user_ids", new_callable=AsyncMock, return_value=admin_ids), \
         patch("app.services.sla_cron.notify_users", new_callable=AsyncMock) as mock_notify_users:
        from app.services.sla_cron import sla_cron_job
        await sla_cron_job()

    mock_notify_users.assert_called_once()
    call_kwargs = mock_notify_users.call_args[1]
    assert call_kwargs["user_ids"] == admin_ids
    assert call_kwargs["notification_type"] == "sla_breach"


@pytest.mark.asyncio
async def test_sla_admin_fallback_24h() -> None:
    """24h after SLA → admin fallback notification."""
    sla = datetime.now(timezone.utc) - timedelta(hours=25)
    epic = _make_epic(sla_due_at=sla, owner_id=uuid4())

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [epic]

    admin_ids = [uuid4()]
    db = _mock_db(mock_result)
    mock_session_local = MagicMock(return_value=db)

    with patch("app.services.sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.sla_cron.get_admin_user_ids", new_callable=AsyncMock, return_value=admin_ids), \
         patch("app.services.sla_cron.notify_users", new_callable=AsyncMock) as mock_notify_users:
        from app.services.sla_cron import sla_cron_job
        await sla_cron_job()

    mock_notify_users.assert_called_once()
    call_kwargs = mock_notify_users.call_args[1]
    assert call_kwargs["notification_type"] == "sla_admin_fallback"


@pytest.mark.asyncio
async def test_sla_cron_skips_done_epics() -> None:
    """Done/cancelled epics should not trigger SLA checks — query excludes them."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    db = _mock_db(mock_result)
    mock_session_local = MagicMock(return_value=db)

    with patch("app.services.sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.sla_cron.create_notification", new_callable=AsyncMock) as mock_notify:
        from app.services.sla_cron import sla_cron_job
        await sla_cron_job()

    mock_notify.assert_not_called()
