"""Unit-Tests für Decision-Request SLA Enforcement Cron (TASK-6-004)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _make_dr(*, age_hours, state="open", task_id=None, owner_id=None, backup_owner_id=None, sla_due_at=None):
    """Create a mock DecisionRequest with given age."""
    dr = MagicMock()
    dr.id = uuid4()
    dr.state = state
    dr.task_id = task_id or uuid4()
    dr.epic_id = uuid4()
    dr.owner_id = owner_id or uuid4()
    dr.backup_owner_id = backup_owner_id
    dr.created_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    dr.sla_due_at = sla_due_at or (datetime.now(timezone.utc) - timedelta(hours=age_hours - 24))
    dr.version = 0
    return dr


def _make_task(*, state="blocked", task_key="TASK-TEST-001"):
    task = MagicMock()
    task.id = uuid4()
    task.task_key = task_key
    task.state = state
    task.version = 0
    return task


def _mock_db_with_drs(drs, task=None):
    """Build a mock DB that returns the given DRs and optionally a task."""
    call_count = {"n": 0}

    async def mock_execute(query, *args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()

        # First call returns DRs, subsequent calls return task or scalar
        if call_count["n"] == 1:
            result.scalars.return_value.all.return_value = drs
        elif task is not None:
            result.scalar_one_or_none.return_value = task
            result.scalar.return_value = task.task_key if hasattr(task, "task_key") else None
        else:
            result.scalar_one_or_none.return_value = None
            result.scalar.return_value = None
        return result

    mock_db = AsyncMock()
    mock_db.execute = mock_execute
    # async with AsyncSessionLocal() as db:
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)
    # async with db.begin(): — must be sync return of async CM
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    mock_db.begin = MagicMock(return_value=begin_cm)
    mock_db.flush = AsyncMock()
    return mock_db


@pytest.mark.asyncio
async def test_24h_notifies_owner() -> None:
    """Decision request open >24h but <48h → notify owner."""
    owner = uuid4()
    dr = _make_dr(age_hours=30, owner_id=owner, backup_owner_id=None)

    mock_db = _mock_db_with_drs([dr])
    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.services.decision_sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.decision_sla_cron.create_notification", new_callable=AsyncMock) as mock_notify, \
         patch("app.services.decision_sla_cron._task_key_for_dr", new_callable=AsyncMock, return_value="TASK-1-001"):
        from app.services.decision_sla_cron import decision_sla_cron_job
        await decision_sla_cron_job()

    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args[1]
    assert call_kwargs["user_id"] == owner
    assert call_kwargs["notification_type"] == "decision_request"


@pytest.mark.asyncio
async def test_48h_notifies_backup_owner() -> None:
    """Decision request open >48h but <72h → notify backup_owner."""
    backup = uuid4()
    dr = _make_dr(age_hours=50, backup_owner_id=backup)

    mock_db = _mock_db_with_drs([dr])
    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.services.decision_sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.decision_sla_cron.create_notification", new_callable=AsyncMock) as mock_notify, \
         patch("app.services.decision_sla_cron._task_key_for_dr", new_callable=AsyncMock, return_value="TASK-1-001"):
        from app.services.decision_sla_cron import decision_sla_cron_job
        await decision_sla_cron_job()

    mock_notify.assert_called_once()
    call_kwargs = mock_notify.call_args[1]
    assert call_kwargs["user_id"] == backup
    assert call_kwargs["notification_type"] == "decision_escalated_backup"


@pytest.mark.asyncio
async def test_48h_no_backup_skips() -> None:
    """48h without backup_owner → skip (no notification at this step)."""
    dr = _make_dr(age_hours=50, backup_owner_id=None)

    mock_db = _mock_db_with_drs([dr])
    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.services.decision_sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.decision_sla_cron.create_notification", new_callable=AsyncMock) as mock_notify, \
         patch("app.services.decision_sla_cron._task_key_for_dr", new_callable=AsyncMock, return_value="TASK-1-001"):
        from app.services.decision_sla_cron import decision_sla_cron_job
        await decision_sla_cron_job()

    # Should skip — no notification at 48h without backup owner
    mock_notify.assert_not_called()


@pytest.mark.asyncio
async def test_72h_escalates() -> None:
    """72h → DR expired, task escalated, admins notified."""
    dr = _make_dr(age_hours=73)
    task = _make_task()

    mock_db = _mock_db_with_drs([dr], task=task)
    mock_session_local = MagicMock(return_value=mock_db)

    admin_ids = [uuid4(), uuid4()]

    with patch("app.services.decision_sla_cron.AsyncSessionLocal", mock_session_local), \
         patch("app.services.decision_sla_cron.get_admin_user_ids", new_callable=AsyncMock, return_value=admin_ids), \
         patch("app.services.decision_sla_cron.notify_users", new_callable=AsyncMock) as mock_notify_users, \
         patch("app.services.decision_sla_cron._task_key_for_dr", new_callable=AsyncMock, return_value="TASK-1-001"), \
         patch("app.services.decision_sla_cron.write_audit", new_callable=AsyncMock):
        from app.services.decision_sla_cron import decision_sla_cron_job
        await decision_sla_cron_job()

    # DR should be expired
    assert dr.state == "expired"

    # Admins should be notified
    mock_notify_users.assert_called_once()
    call_kwargs = mock_notify_users.call_args[1]
    assert call_kwargs["notification_type"] == "decision_escalated_admin"
    assert call_kwargs["user_ids"] == admin_ids
