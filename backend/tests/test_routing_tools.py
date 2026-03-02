"""Unit tests for MCP assign_bug tool (TASK-7-010)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.tools.routing_tools import _handle_assign_bug


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_db(*execute_results: object) -> AsyncMock:
    db = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)

    tx = AsyncMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    db.begin = MagicMock(return_value=tx)

    db.execute = AsyncMock(side_effect=list(execute_results))
    db.flush = AsyncMock()
    return db


def _payload(response: list) -> dict:
    return json.loads(response[0].text)


def _status(response: list) -> int:
    payload = _payload(response)
    if "error" in payload:
        return int(payload["error"]["status"])
    return 200


@pytest.mark.asyncio
async def test_assign_bug_denies_non_admin_role() -> None:
    response = await _handle_assign_bug(
        {
            "bug_report_id": str(uuid.uuid4()),
            "epic_id": str(uuid.uuid4()),
            "_actor_role": "developer",
        }
    )
    assert _status(response) == 403


@pytest.mark.asyncio
async def test_assign_bug_returns_404_for_invalid_bug_report_id() -> None:
    response = await _handle_assign_bug(
        {
            "bug_report_id": "not-a-uuid",
            "epic_id": str(uuid.uuid4()),
            "_actor_role": "admin",
        }
    )
    payload = _payload(response)
    assert payload["error"]["code"] == "ENTITY_NOT_FOUND"
    assert _status(response) == 404


@pytest.mark.asyncio
async def test_assign_bug_returns_404_for_invalid_epic_id() -> None:
    response = await _handle_assign_bug(
        {
            "bug_report_id": str(uuid.uuid4()),
            "epic_id": "not-a-uuid",
            "_actor_role": "admin",
        }
    )
    payload = _payload(response)
    assert payload["error"]["code"] == "ENTITY_NOT_FOUND"
    assert _status(response) == 404


@pytest.mark.asyncio
async def test_assign_bug_returns_404_when_bug_report_missing() -> None:
    db = _mock_db(_scalar_result(None))

    with patch("app.mcp.tools.routing_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        response = await _handle_assign_bug(
            {
                "bug_report_id": str(uuid.uuid4()),
                "epic_id": str(uuid.uuid4()),
                "_actor_role": "admin",
            }
        )

    assert _status(response) == 404


@pytest.mark.asyncio
async def test_assign_bug_returns_404_when_epic_missing() -> None:
    report = MagicMock()
    report.manually_routed = False
    db = _mock_db(_scalar_result(report), _scalar_result(None))

    with patch("app.mcp.tools.routing_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        response = await _handle_assign_bug(
            {
                "bug_report_id": str(uuid.uuid4()),
                "epic_id": str(uuid.uuid4()),
                "_actor_role": "admin",
            }
        )

    assert _status(response) == 404


@pytest.mark.asyncio
async def test_assign_bug_returns_409_when_already_manually_routed_without_force() -> None:
    report = MagicMock()
    report.manually_routed = True
    epic = MagicMock()
    db = _mock_db(_scalar_result(report), _scalar_result(epic))

    with patch("app.mcp.tools.routing_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        response = await _handle_assign_bug(
            {
                "bug_report_id": str(uuid.uuid4()),
                "epic_id": str(uuid.uuid4()),
                "force": False,
                "_actor_role": "admin",
            }
        )

    assert _status(response) == 409


@pytest.mark.asyncio
async def test_assign_bug_force_true_allows_override() -> None:
    report = MagicMock()
    report.manually_routed = True
    epic = MagicMock()
    bug_report_id = uuid.uuid4()
    epic_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    db = _mock_db(_scalar_result(report), _scalar_result(epic))

    with patch("app.mcp.tools.routing_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch("app.mcp.tools.routing_tools.write_audit", new=AsyncMock()):
            with patch("app.mcp.tools.routing_tools.event_bus.publish"):
                response = await _handle_assign_bug(
                    {
                        "bug_report_id": str(bug_report_id),
                        "epic_id": str(epic_id),
                        "force": True,
                        "_actor_role": "admin",
                        "_actor_id": str(actor_id),
                    }
                )

    assert _status(response) == 200
    assert report.epic_id == epic_id
    assert report.manually_routed is True


@pytest.mark.asyncio
async def test_assign_bug_success_sets_fields_writes_audit_and_emits_event() -> None:
    report = MagicMock()
    report.manually_routed = False
    epic = MagicMock()
    bug_report_id = uuid.uuid4()
    epic_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    db = _mock_db(_scalar_result(report), _scalar_result(epic))

    with patch("app.mcp.tools.routing_tools.AsyncSessionLocal", MagicMock(return_value=db)):
        with patch("app.mcp.tools.routing_tools.write_audit", new=AsyncMock()) as write_audit:
            with patch("app.mcp.tools.routing_tools.event_bus.publish") as publish:
                response = await _handle_assign_bug(
                    {
                        "bug_report_id": str(bug_report_id),
                        "epic_id": str(epic_id),
                        "reason": "manual triage",
                        "_actor_role": "admin",
                        "_actor_id": str(actor_id),
                    }
                )

    assert _status(response) == 200

    payload = _payload(response)["data"]
    assert payload["bug_report_id"] == str(bug_report_id)
    assert payload["epic_id"] == str(epic_id)
    assert payload["reason"] == "manual triage"
    assert payload["manually_routed_by"] == str(actor_id)

    assert report.epic_id == epic_id
    assert report.manually_routed is True
    assert report.manually_routed_by == actor_id
    assert report.manually_routed_at is not None

    write_audit.assert_awaited_once()
    audit_kwargs = write_audit.await_args.kwargs
    assert audit_kwargs["tool_name"] == "assign_bug"
    assert audit_kwargs["actor_id"] == actor_id
    assert audit_kwargs["actor_role"] == "admin"
    assert audit_kwargs["input_payload"]["bug_report_id"] == str(bug_report_id)
    assert audit_kwargs["input_payload"]["epic_id"] == str(epic_id)
    assert audit_kwargs["input_payload"]["reason"] == "manual triage"

    publish.assert_called_once_with(
        "bug_manually_routed",
        {
            "bug_report_id": str(bug_report_id),
            "epic_id": str(epic_id),
            "actor_id": str(actor_id),
            "reason": "manual triage",
        },
        channel="triage",
    )
