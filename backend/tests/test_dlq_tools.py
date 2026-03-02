"""Unit tests for MCP DLQ tools (TASK-7-008)."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.tools.dlq_tools import _handle_discard_dead_letter, _handle_requeue_dead_letter
from app.services.dlq_service import DlqError


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=tx)

    return db


def _parse_status(response: list) -> int:
    payload = json.loads(response[0].text)
    if "error" in payload:
        return int(payload["error"]["status"])
    return 200


@pytest.mark.asyncio
async def test_requeue_dead_letter_success_uses_shared_service() -> None:
    db = _mock_db()
    actor_id = str(uuid.uuid4())
    dead_letter_id = str(uuid.uuid4())
    service_result = {
        "id": dead_letter_id,
        "status": "requeued",
        "new_outbox_id": str(uuid.uuid4()),
        "requeued_by": actor_id,
        "requeued_at": "2026-03-01T12:00:00+00:00",
    }

    with patch("app.mcp.tools.dlq_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch("app.mcp.tools.dlq_tools.requeue_dead_letter", new=AsyncMock(return_value=service_result)) as requeue:
            result = await _handle_requeue_dead_letter(
                {"id": dead_letter_id, "_actor_role": "triage", "_actor_id": actor_id}
            )

    assert _parse_status(result) == 200
    payload = json.loads(result[0].text)
    assert payload["data"]["status"] == "requeued"
    requeue.assert_awaited_once_with(db, uuid.UUID(dead_letter_id), uuid.UUID(actor_id))


@pytest.mark.asyncio
async def test_requeue_dead_letter_returns_404_when_missing() -> None:
    db = _mock_db()
    dead_letter_id = str(uuid.uuid4())

    with patch("app.mcp.tools.dlq_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.mcp.tools.dlq_tools.requeue_dead_letter",
            new=AsyncMock(side_effect=DlqError("ENTITY_NOT_FOUND", "missing", 404)),
        ):
            result = await _handle_requeue_dead_letter({"id": dead_letter_id, "_actor_role": "admin"})

    assert _parse_status(result) == 404


@pytest.mark.asyncio
async def test_requeue_dead_letter_returns_409_on_conflict() -> None:
    db = _mock_db()
    dead_letter_id = str(uuid.uuid4())

    with patch("app.mcp.tools.dlq_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.mcp.tools.dlq_tools.requeue_dead_letter",
            new=AsyncMock(side_effect=DlqError("CONFLICT", "already requeued", 409)),
        ):
            result = await _handle_requeue_dead_letter({"id": dead_letter_id, "_actor_role": "admin"})

    assert _parse_status(result) == 409


@pytest.mark.asyncio
async def test_discard_dead_letter_success_uses_shared_service() -> None:
    db = _mock_db()
    actor_id = str(uuid.uuid4())
    dead_letter_id = str(uuid.uuid4())
    service_result = {
        "id": dead_letter_id,
        "status": "discarded",
        "discarded_by": actor_id,
        "discarded_at": "2026-03-01T12:00:00+00:00",
    }

    with patch("app.mcp.tools.dlq_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch("app.mcp.tools.dlq_tools.discard_dead_letter", new=AsyncMock(return_value=service_result)) as discard:
            result = await _handle_discard_dead_letter(
                {"id": dead_letter_id, "_actor_role": "admin", "_actor_id": actor_id}
            )

    assert _parse_status(result) == 200
    payload = json.loads(result[0].text)
    assert payload["data"]["status"] == "discarded"
    discard.assert_awaited_once_with(db, uuid.UUID(dead_letter_id), uuid.UUID(actor_id))


@pytest.mark.asyncio
async def test_discard_dead_letter_returns_409_when_already_discarded() -> None:
    db = _mock_db()
    dead_letter_id = str(uuid.uuid4())

    with patch("app.mcp.tools.dlq_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch(
            "app.mcp.tools.dlq_tools.discard_dead_letter",
            new=AsyncMock(side_effect=DlqError("CONFLICT", "already discarded", 409)),
        ):
            result = await _handle_discard_dead_letter({"id": dead_letter_id, "_actor_role": "admin"})

    assert _parse_status(result) == 409


@pytest.mark.asyncio
async def test_dlq_tools_enforce_role_admin_or_triage() -> None:
    result = await _handle_requeue_dead_letter({"id": str(uuid.uuid4()), "_actor_role": "developer"})
    assert _parse_status(result) == 403


@pytest.mark.asyncio
async def test_dlq_tools_validate_dead_letter_id() -> None:
    result = await _handle_discard_dead_letter({"id": "not-a-uuid", "_actor_role": "admin"})
    assert _parse_status(result) == 422
