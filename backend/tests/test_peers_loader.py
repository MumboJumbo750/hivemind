"""Unit-Tests für den peers.yaml-Loader (TASK-F-002)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.peers_loader import load_peers


@pytest.fixture
def _enable_federation(monkeypatch: pytest.MonkeyPatch):
    from app import config
    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", True)


@pytest.fixture
def _disable_federation(monkeypatch: pytest.MonkeyPatch):
    from app import config
    monkeypatch.setattr(config.settings, "hivemind_federation_enabled", False)


VALID_YAML = """\
peers:
  - name: ben-hivemind
    url: http://192.168.1.11:8000
    public_key: "ed25519:pub:abc123"
  - name: clara-hivemind
    url: http://192.168.1.12:8000
    public_key: "ed25519:pub:def456"
"""


@pytest.mark.asyncio
@pytest.mark.usefixtures("_disable_federation")
async def test_skip_when_federation_disabled() -> None:
    db = AsyncMock()
    await load_peers(db)
    db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_skip_when_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config
    monkeypatch.setattr(config.settings, "hivemind_peers_config", "/nonexistent/peers.yaml")
    db = AsyncMock()
    await load_peers(db)
    db.execute.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_loads_peers_from_yaml(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    peers_file = tmp_path / "peers.yaml"
    peers_file.write_text(VALID_YAML, encoding="utf-8")
    monkeypatch.setattr(config.settings, "hivemind_peers_config", str(peers_file))

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None  # no existing peers
    db.execute.return_value = execute_result

    await load_peers(db)

    # Two peers should be added
    assert db.add.call_count == 2
    added_nodes = [call[0][0] for call in db.add.call_args_list]
    assert added_nodes[0].node_name == "ben-hivemind"
    assert added_nodes[0].node_url == "http://192.168.1.11:8000"
    assert added_nodes[1].node_name == "clara-hivemind"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_updates_existing_peer(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    peers_file = tmp_path / "peers.yaml"
    peers_file.write_text(VALID_YAML, encoding="utf-8")
    monkeypatch.setattr(config.settings, "hivemind_peers_config", str(peers_file))

    # Simulate first peer exists with different name
    existing_node = MagicMock()
    existing_node.node_name = "old-name"
    existing_node.public_key = "ed25519:pub:abc123"

    db = AsyncMock()
    call_count = 0

    def _make_result(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        if call_count == 1:
            result.scalar_one_or_none.return_value = existing_node
        else:
            result.scalar_one_or_none.return_value = None
        return result

    db.execute.side_effect = _make_result

    await load_peers(db)

    # First peer updated name, second peer added
    assert existing_node.node_name == "ben-hivemind"
    assert db.add.call_count == 1  # only the second peer is new


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_skips_invalid_entries(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    yaml_content = """\
peers:
  - name: missing-url
    public_key: "ed25519:pub:abc"
  - name: valid
    url: http://valid:8000
    public_key: "ed25519:pub:def"
"""
    peers_file = tmp_path / "peers.yaml"
    peers_file.write_text(yaml_content, encoding="utf-8")
    monkeypatch.setattr(config.settings, "hivemind_peers_config", str(peers_file))

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    await load_peers(db)

    # Only the valid entry should be added
    assert db.add.call_count == 1
    assert db.add.call_args[0][0].node_name == "valid"


@pytest.mark.asyncio
@pytest.mark.usefixtures("_enable_federation")
async def test_handles_invalid_yaml(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import config

    peers_file = tmp_path / "peers.yaml"
    peers_file.write_text("{{invalid yaml: [", encoding="utf-8")
    monkeypatch.setattr(config.settings, "hivemind_peers_config", str(peers_file))

    db = AsyncMock()
    # Should not crash
    await load_peers(db)
    db.add.assert_not_called()
