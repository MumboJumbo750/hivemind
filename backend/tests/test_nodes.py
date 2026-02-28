"""Tests for nodes router — TASK-F-012."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.nodes import (
    PeerCreate,
    PeerUpdate,
    FederationSettingsUpdate,
    get_node_identity,
    list_nodes,
    create_node,
    update_node,
    delete_node,
    get_federation_settings,
    update_federation_settings,
)


def _make_identity(node_id=None, name="alpha", url="http://alpha:8000", pub="ssh-ed25519 AAA"):
    nid = node_id or uuid.uuid4()
    ident = MagicMock()
    ident.node_id = nid
    ident.node_name = name
    ident.public_key = pub
    return ident, nid


def _make_node(node_id=None, name="beta", url="http://beta:8000", status="active"):
    n = MagicMock()
    n.id = node_id or uuid.uuid4()
    n.node_name = name
    n.node_url = url
    n.public_key = "ssh-ed25519 BBB"
    n.status = status
    n.last_seen = datetime.now(timezone.utc)
    n.deleted_at = None
    return n


# ─── get_node_identity ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_node_identity_ok():
    ident, nid = _make_identity()
    node = _make_node(node_id=nid, name="alpha", url="http://alpha:8000")

    db = AsyncMock()
    call_count = 0
    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = ident
        else:
            r.scalar_one_or_none.return_value = node
        return r
    db.execute = AsyncMock(side_effect=fake_execute)

    resp = await get_node_identity(db=db)
    assert resp.node_id == nid
    assert resp.node_name == "alpha"
    assert resp.public_key == "ssh-ed25519 AAA"


@pytest.mark.asyncio
async def test_get_node_identity_missing():
    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    db.execute.return_value = r

    with pytest.raises(Exception) as exc_info:
        await get_node_identity(db=db)
    assert exc_info.value.status_code == 404


# ─── list_nodes ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_nodes_excludes_self():
    own_id = uuid.uuid4()
    ident, _ = _make_identity(node_id=own_id)
    peer = _make_node(name="beta")

    db = AsyncMock()
    call_count = 0
    async def fake_execute(stmt):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            # Node list query
            own_node = _make_node(node_id=own_id, name="alpha")
            r.scalars.return_value.all.return_value = [own_node, peer]
        else:
            r.scalar_one_or_none.return_value = ident
        return r
    db.execute = AsyncMock(side_effect=fake_execute)

    resp = await list_nodes(db=db)
    assert len(resp) == 1
    assert resp[0].node_name == "beta"


# ─── create_node ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_node_ok():
    db = AsyncMock()
    # No existing node with same URL
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    db.execute.return_value = r

    new_id = uuid.uuid4()

    async def fake_refresh(obj):
        obj.id = new_id
        obj.status = "active"
        obj.last_seen = None
    db.refresh = AsyncMock(side_effect=fake_refresh)

    body = PeerCreate(node_name="gamma", node_url="http://gamma:8000")
    resp = await create_node(body=body, db=db)
    assert resp.node_name == "gamma"
    assert resp.id == new_id
    db.add.assert_called_once()
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_node_duplicate_url():
    db = AsyncMock()
    existing = _make_node()
    r = MagicMock()
    r.scalar_one_or_none.return_value = existing
    db.execute.return_value = r

    body = PeerCreate(node_name="dup", node_url="http://beta:8000")
    with pytest.raises(Exception) as exc_info:
        await create_node(body=body, db=db)
    assert exc_info.value.status_code == 409


# ─── update_node ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_node_block():
    node = _make_node()
    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = node
    db.execute.return_value = r
    db.refresh = AsyncMock()

    body = PeerUpdate(status="blocked")
    resp = await update_node(node_id=node.id, body=body, db=db)
    assert node.status == "blocked"
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_update_node_not_found():
    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    db.execute.return_value = r

    body = PeerUpdate(status="blocked")
    with pytest.raises(Exception) as exc_info:
        await update_node(node_id=uuid.uuid4(), body=body, db=db)
    assert exc_info.value.status_code == 404


# ─── delete_node ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_node_ok():
    node = _make_node()
    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = node
    db.execute.return_value = r

    await delete_node(node_id=node.id, db=db)
    assert node.deleted_at is not None
    db.commit.assert_awaited()


# ─── federation settings ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_federation_settings():
    resp = await get_federation_settings()
    assert resp.topology in ("direct_mesh", "hub_assisted", "hub_relay")
    assert isinstance(resp.heartbeat_interval, int)


@pytest.mark.asyncio
async def test_update_federation_settings_topology():
    body = FederationSettingsUpdate(topology="hub_relay")
    resp = await update_federation_settings(body=body)
    assert resp.topology == "hub_relay"

    # Restore default
    body2 = FederationSettingsUpdate(topology="direct_mesh")
    await update_federation_settings(body=body2)
