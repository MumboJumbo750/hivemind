"""Unit-Tests für Audit-Retention-Cron (TASK-2-007)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_retention_nullifies_old_payloads() -> None:
    """Job nullt Payloads für Einträge älter als AUDIT_RETENTION_DAYS."""
    mock_result = MagicMock()
    mock_result.rowcount = 5

    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    mock_session_local = MagicMock(return_value=mock_db)

    with patch("app.services.scheduler.AsyncSessionLocal", mock_session_local):
        from app.services.scheduler import _audit_retention_job
        await _audit_retention_job()

    mock_db.execute.assert_called_once()
    mock_db.commit.assert_called_once()
    # SQL enthält UPDATE mcp_invocations
    sql_call = str(mock_db.execute.call_args[0][0])
    assert "mcp_invocations" in sql_call.lower() or "UPDATE" in sql_call.upper()


@pytest.mark.asyncio
async def test_retention_uses_configured_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """AUDIT_RETENTION_DAYS aus Config wird für Cutoff genutzt."""
    from app import config
    monkeypatch.setattr(config.settings, "audit_retention_days", 30)

    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db = AsyncMock()
    mock_db.execute.return_value = mock_result
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.scheduler.AsyncSessionLocal", MagicMock(return_value=mock_db)):
        from app.services.scheduler import _audit_retention_job
        await _audit_retention_job()

    # Cutoff sollte ~30 Tage in der Vergangenheit liegen
    call_params = mock_db.execute.call_args[0][1]
    cutoff: datetime = call_params["cutoff"]
    expected = datetime.now(timezone.utc) - timedelta(days=30)
    assert abs((cutoff - expected).total_seconds()) < 5
