"""Unit tests for audit retention cron (TASK-2-007 / TASK-7-011)."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_retention_nullifies_payloads_and_deletes_old_rows() -> None:
    """The job performs payload nullification and row deletion in one run."""
    nullify_result = MagicMock()
    nullify_result.rowcount = 5
    delete_result = MagicMock()
    delete_result.rowcount = 2

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [nullify_result, delete_result]
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.db.AsyncSessionLocal", MagicMock(return_value=mock_db)):
        from app.services.scheduler import _audit_retention_job

        await _audit_retention_job()

    assert mock_db.execute.call_count == 2
    mock_db.commit.assert_called_once()

    nullify_sql = str(mock_db.execute.call_args_list[0].args[0]).upper()
    delete_sql = str(mock_db.execute.call_args_list[1].args[0]).upper()
    assert "UPDATE MCP_INVOCATIONS" in nullify_sql
    assert "DELETE FROM MCP_INVOCATIONS" in delete_sql
    assert "payload_cutoff" in mock_db.execute.call_args_list[0].args[1]
    assert "delete_cutoff" in mock_db.execute.call_args_list[1].args[1]


@pytest.mark.asyncio
async def test_retention_uses_configured_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nullify and delete cutoffs come from independent settings."""
    from app import config

    monkeypatch.setattr(config.settings, "audit_retention_days", 30)
    monkeypatch.setattr(config.settings, "audit_row_deletion_days", 120)

    nullify_result = MagicMock()
    nullify_result.rowcount = 0
    delete_result = MagicMock()
    delete_result.rowcount = 0

    mock_db = AsyncMock()
    mock_db.execute.side_effect = [nullify_result, delete_result]
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    with patch("app.db.AsyncSessionLocal", MagicMock(return_value=mock_db)):
        from app.services.scheduler import _audit_retention_job

        await _audit_retention_job()

    payload_cutoff: datetime = mock_db.execute.call_args_list[0].args[1]["payload_cutoff"]
    delete_cutoff: datetime = mock_db.execute.call_args_list[1].args[1]["delete_cutoff"]

    expected_payload = datetime.now(UTC) - timedelta(days=30)
    expected_delete = datetime.now(UTC) - timedelta(days=120)
    assert abs((payload_cutoff - expected_payload).total_seconds()) < 5
    assert abs((delete_cutoff - expected_delete).total_seconds()) < 5
