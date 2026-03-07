from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.admin import ProviderStatus, _preview_error, get_sync_status
from app.schemas.auth import CurrentActor


def _scalar_result(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _rows_result(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = rows
    return result


def _actor() -> CurrentActor:
    return CurrentActor(
        id=uuid.uuid4(),
        username="admin",
        role="admin",
    )


@pytest.mark.asyncio
async def test_get_sync_status_aggregates_queue_sync_and_provider_data() -> None:
    now = datetime(2026, 3, 1, 10, 30, tzinfo=UTC)
    delivered_row = SimpleNamespace(
        id=uuid.uuid4(),
        created_at=now,
        direction="inbound",
        entity_type="task",
    )
    failed_row = SimpleNamespace(
        id=uuid.uuid4(),
        failed_at=now,
        error="HTTP 500 from YouTrack with a very long body",
        attempts=3,
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_result(4),  # pending_outbound
            _scalar_result(2),  # pending_inbound
            _scalar_result(1),  # dead_letters
            _scalar_result(7),  # delivered_today
            _rows_result([delivered_row]),
            _rows_result([failed_row]),  # dead_letter_rows
            _rows_result([]),  # retry_rows
        ]
    )

    ollama = ProviderStatus(state="online", detail="reachable", checked_at=now)
    youtrack = ProviderStatus(state="degraded", detail="auth failed", checked_at=now)
    with patch("app.routers.admin._check_ollama_status", new=AsyncMock(return_value=ollama)), patch(
        "app.routers.admin._check_youtrack_status",
        new=AsyncMock(return_value=youtrack),
    ):
        result = await get_sync_status(db=db, actor=_actor())

    assert result.queue.pending_outbound == 4
    assert result.queue.pending_inbound == 2
    assert result.queue.dead_letters == 1
    assert result.queue.delivered_today == 7

    assert len(result.recent_delivered) == 1
    assert result.recent_delivered[0].direction == "inbound"
    assert result.recent_delivered[0].payload_type == "task"

    assert len(result.recent_failed) == 1
    assert result.recent_failed[0].attempts == 3
    assert result.recent_failed[0].last_error.startswith("HTTP 500")
    assert result.recent_failed[0].dlq_url.startswith("/triage")

    assert result.providers.ollama.state == "online"
    assert result.providers.youtrack.state == "degraded"


def test_delivered_filter_uses_only_valid_states() -> None:
    """delivered_filter darf state=='delivered' nicht enthalten (existiert nie).

    Erfolgreiche Outbound-Einträge werden gelöscht, nicht auf 'delivered' gesetzt.
    Nur routed inbound Einträge sollen gezählt werden.
    Die Logik liegt jetzt in dlq_service (nach Sync/Outbox-Domain-Refactoring).
    """
    import inspect

    from app.services.dlq_service import get_admin_delivered_rows, get_queue_stats

    for fn in (get_admin_delivered_rows, get_queue_stats):
        src = inspect.getsource(fn)
        assert 'state == "delivered"' not in src, (
            f"{fn.__name__}: delivered_filter enthält 'delivered' State — dieser existiert nie im System"
        )

    src_stats = inspect.getsource(get_queue_stats)
    assert 'routing_state == "routed"' in src_stats


def test_preview_error_compacts_and_truncates_text() -> None:
    raw = "line 1\nline 2\tline 3 " + ("x" * 300)
    preview = _preview_error(raw, max_length=40)
    assert "\n" not in preview
    assert "\t" not in preview
    assert preview.endswith("...")
    assert len(preview) == 43
