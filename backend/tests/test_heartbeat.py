"""Tests for Heartbeat Service — TASK-F-010."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _make_peer(status="active", last_seen=None, node_url="http://peer1:8000"):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.node_name = "peer-1"
    p.node_url = node_url
    p.status = status
    p.last_seen = last_seen or datetime.now(timezone.utc)
    p.deleted_at = None
    return p


@pytest.mark.asyncio
async def test_heartbeat_updates_last_seen_on_success():
    """Successful ping updates last_seen and keeps status active."""
    from app.services.heartbeat import heartbeat

    peer = _make_peer(status="active", last_seen=datetime.now(timezone.utc) - timedelta(minutes=2))
    old_last_seen = peer.last_seen

    mock_db = AsyncMock()
    r = MagicMock()
    r.scalars.return_value.all.return_value = [peer]
    mock_db.execute.return_value = r

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.heartbeat.settings") as mock_settings, \
         patch("app.services.heartbeat.AsyncSessionLocal") as mock_session_cls, \
         patch("app.services.heartbeat.httpx.AsyncClient") as mock_client_cls:

        mock_settings.hivemind_federation_enabled = True
        mock_settings.hivemind_peer_timeout = 900

        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await heartbeat()

    assert peer.status == "active"
    assert peer.last_seen > old_last_seen


@pytest.mark.asyncio
async def test_heartbeat_marks_inactive_on_timeout():
    """Peer is set to inactive when last_seen exceeds timeout."""
    from app.services.heartbeat import heartbeat

    # Peer last seen 20 minutes ago (timeout is 15 min = 900s)
    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    peer = _make_peer(status="active", last_seen=old_time)

    mock_db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalars.return_value.all.return_value = [peer]
        else:
            r.scalar_one_or_none.return_value = None  # no delegated tasks
        return r

    mock_db.execute.side_effect = _execute

    with patch("app.services.heartbeat.settings") as mock_settings, \
         patch("app.services.heartbeat.AsyncSessionLocal") as mock_session_cls, \
         patch("app.services.heartbeat.httpx.AsyncClient") as mock_client_cls:

        mock_settings.hivemind_federation_enabled = True
        mock_settings.hivemind_peer_timeout = 900

        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await heartbeat()

    assert peer.status == "inactive"


@pytest.mark.asyncio
async def test_heartbeat_reactivates_peer():
    """Peer goes from inactive back to active on successful ping."""
    from app.services.heartbeat import heartbeat

    peer = _make_peer(status="inactive", last_seen=datetime.now(timezone.utc) - timedelta(minutes=20))

    mock_db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalars.return_value.all.return_value = [peer]
        return r

    mock_db.execute.side_effect = _execute

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.heartbeat.settings") as mock_settings, \
         patch("app.services.heartbeat.AsyncSessionLocal") as mock_session_cls, \
         patch("app.services.heartbeat.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.heartbeat._emit_peer_event", new_callable=AsyncMock) as mock_emit:

        mock_settings.hivemind_federation_enabled = True
        mock_settings.hivemind_peer_timeout = 900

        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await heartbeat()

    assert peer.status == "active"
    mock_emit.assert_awaited_once_with(mock_db, peer, "peer_online")


@pytest.mark.asyncio
async def test_heartbeat_emits_peer_offline_with_delegated_tasks():
    """peer_offline event emitted when inactive peer has delegated tasks."""
    from app.services.heartbeat import heartbeat

    old_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    peer = _make_peer(status="active", last_seen=old_time)

    mock_db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalars.return_value.all.return_value = [peer]
        else:
            r.scalar_one_or_none.return_value = uuid.uuid4()  # has delegated tasks
        return r

    mock_db.execute.side_effect = _execute

    with patch("app.services.heartbeat.settings") as mock_settings, \
         patch("app.services.heartbeat.AsyncSessionLocal") as mock_session_cls, \
         patch("app.services.heartbeat.httpx.AsyncClient") as mock_client_cls, \
         patch("app.services.heartbeat._emit_peer_event", new_callable=AsyncMock) as mock_emit:

        mock_settings.hivemind_federation_enabled = True
        mock_settings.hivemind_peer_timeout = 900

        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await heartbeat()

    assert peer.status == "inactive"
    mock_emit.assert_awaited_once_with(mock_db, peer, "peer_offline")


@pytest.mark.asyncio
async def test_heartbeat_disabled_when_not_federation():
    """Heartbeat does nothing when federation is disabled."""
    from app.services.heartbeat import heartbeat

    with patch("app.services.heartbeat.settings") as mock_settings, \
         patch("app.services.heartbeat.AsyncSessionLocal") as mock_session_cls:

        mock_settings.hivemind_federation_enabled = False
        await heartbeat()

        mock_session_cls.assert_not_called()
