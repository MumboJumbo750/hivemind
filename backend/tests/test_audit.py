"""Unit-Tests für Audit-Writer (TASK-2-006)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.audit import write_audit_sync


@pytest.mark.asyncio
async def test_write_audit_sync_creates_invocation() -> None:
    """write_audit_sync erzeugt einen McpInvocation-Eintrag."""
    db = AsyncMock()

    actor_id = uuid.uuid4()
    await write_audit_sync(
        db=db,
        tool_name="update_task",
        actor_id=actor_id,
        actor_role="developer",
        input_payload={"title": "neu"},
        output_payload={"task_key": "TASK-1"},
        epic_id=uuid.uuid4(),
        target_id="TASK-1",
        duration_ms=42,
    )

    db.add.assert_called_once()
    db.flush.assert_called_once()

    added = db.add.call_args[0][0]
    assert added.tool_name == "update_task"
    assert added.actor_id == actor_id
    assert added.actor_role == "developer"
    assert added.duration_ms == 42
    assert added.status == "completed"


@pytest.mark.asyncio
async def test_write_audit_sync_with_idempotency_key() -> None:
    """Idempotency-Key wird korrekt weitergegeben."""
    db = AsyncMock()
    idem_key = uuid.uuid4()

    await write_audit_sync(
        db=db,
        tool_name="update_epic",
        actor_id=uuid.uuid4(),
        actor_role="admin",
        idempotency_key=idem_key,
    )

    added = db.add.call_args[0][0]
    assert added.idempotency_key == idem_key
