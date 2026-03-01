"""Unit-Tests für Notification Retention Cron (TASK-6-009)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: build an async context-manager mock for AsyncSessionLocal
# ---------------------------------------------------------------------------
def _make_db_mock(read_rowcount: int = 0, unread_rowcount: int = 0):
    mock_result_read = MagicMock(rowcount=read_rowcount)
    mock_result_unread = MagicMock(rowcount=unread_rowcount)

    call_count = {"n": 0}

    async def _execute(query, params=None):
        call_count["n"] += 1
        return mock_result_read if call_count["n"] == 1 else mock_result_unread

    db = AsyncMock()
    db.execute = _execute          # plain async function
    db.commit = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notification_retention_deletes_old_read() -> None:
    """Read notifications older than NOTIFICATION_RETENTION_DAYS are deleted."""
    db = _make_db_mock(read_rowcount=15, unread_rowcount=0)

    with patch("app.db.AsyncSessionLocal", MagicMock(return_value=db)):
        from app.services.scheduler import _notification_retention_job
        await _notification_retention_job()

    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_notification_retention_deletes_old_unread() -> None:
    """Unread notifications older than NOTIFICATION_UNREAD_RETENTION_DAYS are deleted."""
    db = _make_db_mock(read_rowcount=0, unread_rowcount=7)

    with patch("app.db.AsyncSessionLocal", MagicMock(return_value=db)):
        from app.services.scheduler import _notification_retention_job
        await _notification_retention_job()

    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_notification_retention_uses_config_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config values notification_retention_days and notification_unread_retention_days are used."""
    from app import config

    monkeypatch.setattr(config.settings, "notification_retention_days", 30)
    monkeypatch.setattr(config.settings, "notification_unread_retention_days", 180)

    mock_result = MagicMock(rowcount=0)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.commit = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.db.AsyncSessionLocal", MagicMock(return_value=db)):
        from app.services.scheduler import _notification_retention_job
        await _notification_retention_job()

    # Should have been called twice (read + unread)
    assert db.execute.call_count == 2

    # Check first cutoff (~30 days ago)
    first_call_params = db.execute.call_args_list[0][0][1]
    cutoff_read: datetime = first_call_params["cutoff"]
    expected_read = datetime.now(timezone.utc) - timedelta(days=30)
    assert abs((cutoff_read - expected_read).total_seconds()) < 5

    # Check second cutoff (~180 days ago)
    second_call_params = db.execute.call_args_list[1][0][1]
    cutoff_unread: datetime = second_call_params["cutoff"]
    expected_unread = datetime.now(timezone.utc) - timedelta(days=180)
    assert abs((cutoff_unread - expected_unread).total_seconds()) < 5
