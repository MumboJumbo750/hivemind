"""Unit-Tests für Optimistic Locking + Idempotenz (TASK-2-005)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services.locking import check_version


def test_version_match_passes() -> None:
    entity = MagicMock()
    entity.version = 3
    check_version(entity, 3)  # kein Fehler


def test_version_mismatch_raises_409() -> None:
    entity = MagicMock()
    entity.version = 5
    with pytest.raises(HTTPException) as exc:
        check_version(entity, 3)
    assert exc.value.status_code == 409
    assert "5" in exc.value.detail  # zeigt aktuellen Wert


@pytest.mark.asyncio
async def test_idempotency_returns_none_for_new_key() -> None:
    from app.services.locking import check_idempotency

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    result = await check_idempotency(db, uuid.uuid4(), uuid.uuid4(), "test_tool")
    assert result is None


@pytest.mark.asyncio
async def test_idempotency_returns_cached_body_for_existing_key() -> None:
    from app.services.locking import check_idempotency

    cached_body = {"id": "abc", "state": "done"}
    db = AsyncMock()
    existing = MagicMock()
    existing.response_body = cached_body
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing
    db.execute.return_value = execute_result

    result = await check_idempotency(db, uuid.uuid4(), uuid.uuid4(), "test_tool")
    assert result == cached_body
