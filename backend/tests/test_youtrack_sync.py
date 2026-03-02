"""Unit tests for YouTrack outbound sync service (TASK-7-004)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sync_errors import PermanentSyncError
from app.services.youtrack_sync import YouTrackSyncService


@pytest.fixture
def _youtrack_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_youtrack_url", "https://yt.example.com")
    monkeypatch.setattr(config.settings, "hivemind_youtrack_token", "token-123")
    monkeypatch.setattr(config.settings, "hivemind_youtrack_state_mapping", "")


def _mock_async_client(response: MagicMock) -> AsyncMock:
    client = AsyncMock()
    client.patch.return_value = response
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


@pytest.mark.asyncio
@pytest.mark.usefixtures("_youtrack_env")
async def test_process_outbound_syncs_state_and_assignee() -> None:
    response = MagicMock()
    response.status_code = 200
    response.text = "ok"
    client = _mock_async_client(response)

    entry = MagicMock()
    entry.entity_id = "YT-123"
    entry.payload = {
        "external_id": "YT-123",
        "state": "in_progress",
        "assignee_login": "alice",
    }

    with patch("app.services.youtrack_sync.httpx.AsyncClient", return_value=client):
        service = YouTrackSyncService()
        await service.process_outbound(entry)

    assert client.patch.await_count == 2

    first_payload = client.patch.await_args_list[0].kwargs["json"]
    second_payload = client.patch.await_args_list[1].kwargs["json"]
    assert first_payload["customFields"][0]["value"]["name"] == "In Progress"
    assert second_payload["customFields"][0]["value"]["login"] == "alice"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_youtrack_env")
async def test_process_outbound_4xx_raises_permanent_error() -> None:
    response = MagicMock()
    response.status_code = 404
    response.text = "not found"
    client = _mock_async_client(response)

    entry = MagicMock()
    entry.entity_id = "YT-404"
    entry.payload = {
        "external_id": "YT-404",
        "state": "done",
    }

    with patch("app.services.youtrack_sync.httpx.AsyncClient", return_value=client):
        service = YouTrackSyncService()
        with pytest.raises(PermanentSyncError):
            await service.process_outbound(entry)

    client.patch.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_youtrack_env")
async def test_process_outbound_5xx_raises_retryable_error() -> None:
    response = MagicMock()
    response.status_code = 503
    response.text = "service unavailable"
    client = _mock_async_client(response)

    entry = MagicMock()
    entry.entity_id = "YT-503"
    entry.payload = {
        "external_id": "YT-503",
        "state": "done",
    }

    with patch("app.services.youtrack_sync.httpx.AsyncClient", return_value=client):
        service = YouTrackSyncService()
        with pytest.raises(RuntimeError):
            await service.process_outbound(entry)

    client.patch.assert_awaited_once()


def test_state_mapping_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_youtrack_state_mapping", '{"in_progress":"Doing"}')
    service = YouTrackSyncService()
    assert service.state_mapping["in_progress"] == "Doing"
