"""Unit-Tests für den Node-Bootstrap (TASK-2-001)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.node_bootstrap import bootstrap_node


@pytest.mark.asyncio
async def test_bootstrap_creates_node_and_identity() -> None:
    """Erster Start: Node + NodeIdentity werden angelegt."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None  # kein bestehender Eintrag
    db.execute.return_value = execute_result

    await bootstrap_node(db)

    # Node und NodeIdentity je einmal hinzugefügt
    assert db.add.call_count == 2
    # Zweimal flush (nach Node, nach NodeIdentity)
    assert db.flush.call_count == 2


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent() -> None:
    """Zweiter Start: kein zweiter Node angelegt."""
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = MagicMock()  # bereits vorhanden
    db.execute.return_value = execute_result

    await bootstrap_node(db)

    db.add.assert_not_called()
    db.flush.assert_not_called()


@pytest.mark.asyncio
async def test_bootstrap_uses_config_node_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Node-Name kommt aus HIVEMIND_NODE_NAME config."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_node_name", "test-commander")
    monkeypatch.setattr(config.settings, "hivemind_node_url", "http://test:8000")

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    await bootstrap_node(db)

    added_node = db.add.call_args_list[0][0][0]
    assert added_node.node_name == "test-commander"
    assert added_node.node_url == "http://test:8000"


@pytest.mark.asyncio
async def test_bootstrap_encrypts_private_key_with_passphrase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Private key is encrypted when HIVEMIND_KEY_PASSPHRASE is set."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    from app import config

    monkeypatch.setattr(config.settings, "hivemind_key_passphrase", "test-secret-123")

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    await bootstrap_node(db)

    # Identity is the second add() call
    identity = db.add.call_args_list[1][0][0]
    private_pem = identity.private_key

    # PEM should be encrypted — loading without password must fail
    with pytest.raises(Exception):
        load_pem_private_key(private_pem.encode(), password=None)

    # Loading with correct password must succeed
    key = load_pem_private_key(private_pem.encode(), password=b"test-secret-123")
    assert key is not None


@pytest.mark.asyncio
async def test_bootstrap_no_encryption_without_passphrase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Private key is stored unencrypted when passphrase is empty."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    from app import config

    monkeypatch.setattr(config.settings, "hivemind_key_passphrase", "")

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    await bootstrap_node(db)

    identity = db.add.call_args_list[1][0][0]
    private_pem = identity.private_key

    # PEM should load without password
    key = load_pem_private_key(private_pem.encode(), password=None)
    assert key is not None
