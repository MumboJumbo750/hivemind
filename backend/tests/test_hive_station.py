"""Tests for Hive Station Client — TASK-F-011."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_direct_mesh_skips_register():
    """In direct_mesh mode, register() returns False without HTTP call."""
    from app.services.hive_station import HiveStationClient

    with patch("app.services.hive_station.settings") as mock_settings:
        mock_settings.hivemind_hive_station_url = ""
        mock_settings.hivemind_hive_station_token = ""
        mock_settings.hivemind_federation_topology = "direct_mesh"
        mock_settings.hivemind_hive_relay_enabled = False

        client = HiveStationClient()
        db = AsyncMock()
        result = await client.register(db)

    assert result is False
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_hub_assisted_register_success():
    """hub_assisted mode sends register request to Hive Station."""
    from app.services.hive_station import HiveStationClient

    node_id = uuid.uuid4()
    identity = MagicMock()
    identity.node_id = node_id
    identity.node_name = "test-node"
    identity.public_key = "pubkey123"

    node = MagicMock()
    node.node_url = "http://local:8000"

    db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = identity
        else:
            r.scalar_one_or_none.return_value = node
        return r

    db.execute.side_effect = _execute

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.hive_station.settings") as mock_settings, \
         patch("app.services.hive_station.httpx.AsyncClient") as mock_client_cls:

        mock_settings.hivemind_hive_station_url = "http://hub:9000"
        mock_settings.hivemind_hive_station_token = "secret-token"
        mock_settings.hivemind_federation_topology = "hub_assisted"
        mock_settings.hivemind_hive_relay_enabled = False

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        client = HiveStationClient()
        result = await client.register(db)

    assert result is True
    mock_http.post.assert_awaited_once()
    call_args = mock_http.post.call_args
    assert "register" in call_args[0][0]
    assert "Bearer secret-token" in str(call_args[1].get("headers", {}))


@pytest.mark.asyncio
async def test_hub_assisted_register_fallback():
    """hub_assisted register falls back gracefully on HTTP error."""
    from app.services.hive_station import HiveStationClient

    identity = MagicMock()
    identity.node_id = uuid.uuid4()
    identity.node_name = "test-node"
    identity.public_key = "pubkey"

    node = MagicMock()
    node.node_url = "http://local:8000"

    db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = identity
        else:
            r.scalar_one_or_none.return_value = node
        return r

    db.execute.side_effect = _execute

    with patch("app.services.hive_station.settings") as mock_settings, \
         patch("app.services.hive_station.httpx.AsyncClient") as mock_client_cls:

        mock_settings.hivemind_hive_station_url = "http://hub:9000"
        mock_settings.hivemind_hive_station_token = ""
        mock_settings.hivemind_federation_topology = "hub_assisted"
        mock_settings.hivemind_hive_relay_enabled = False

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        client = HiveStationClient()
        result = await client.register(db)

    assert result is False


@pytest.mark.asyncio
async def test_fetch_peers_merges_into_db():
    """fetch_peers inserts/updates nodes from hub response."""
    from app.services.hive_station import HiveStationClient

    own_id = uuid.uuid4()
    identity = MagicMock()
    identity.node_id = own_id

    db = AsyncMock()
    id_call_done = False

    def _execute(*args, **kwargs):
        nonlocal id_call_done
        r = MagicMock()
        if not id_call_done:
            # First call: NodeIdentity
            r.scalar_one_or_none.return_value = identity
            id_call_done = True
        else:
            # Subsequent calls: Node lookup
            r.scalar_one_or_none.return_value = None  # no existing node
        return r

    db.execute.side_effect = _execute

    peers_response = MagicMock()
    peers_response.status_code = 200
    peers_response.raise_for_status = MagicMock()
    peers_response.json.return_value = [
        {"node_id": str(uuid.uuid4()), "node_name": "peer-a", "node_url": "http://peer-a:8000", "public_key": "pk-a"},
    ]

    with patch("app.services.hive_station.settings") as mock_settings, \
         patch("app.services.hive_station.httpx.AsyncClient") as mock_client_cls:

        mock_settings.hivemind_hive_station_url = "http://hub:9000"
        mock_settings.hivemind_hive_station_token = "tok"
        mock_settings.hivemind_federation_topology = "hub_assisted"
        mock_settings.hivemind_hive_relay_enabled = False

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=peers_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        client = HiveStationClient()
        count = await client.fetch_peers(db)

    assert count == 1
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_relay_sends_to_hive_station():
    """hub_relay mode relays messages through Hive Station."""
    from app.services.hive_station import HiveStationClient

    mock_response = MagicMock()
    mock_response.status_code = 202
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.hive_station.settings") as mock_settings, \
         patch("app.services.hive_station.httpx.AsyncClient") as mock_client_cls:

        mock_settings.hivemind_hive_station_url = "http://hub:9000"
        mock_settings.hivemind_hive_station_token = "tok"
        mock_settings.hivemind_federation_topology = "hub_relay"
        mock_settings.hivemind_hive_relay_enabled = True

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        client = HiveStationClient()
        result = await client.relay("http://peer:8000", "federation/skill/publish", {"title": "test"})

    assert result is True
    mock_http.post.assert_awaited_once()
    call_args = mock_http.post.call_args
    assert "relay/forward" in call_args[0][0]


@pytest.mark.asyncio
async def test_relay_disabled_in_direct_mesh():
    """relay() returns False in direct_mesh mode."""
    from app.services.hive_station import HiveStationClient

    with patch("app.services.hive_station.settings") as mock_settings:
        mock_settings.hivemind_hive_station_url = "http://hub:9000"
        mock_settings.hivemind_hive_station_token = ""
        mock_settings.hivemind_federation_topology = "direct_mesh"
        mock_settings.hivemind_hive_relay_enabled = False

        client = HiveStationClient()
        result = await client.relay("http://peer:8000", "p", {"k": "v"})

    assert result is False
