"""Integration-Tests: E2E Outbox → Sync → DLQ Flow (TASK-7-019).

Alle 6 Szenarien aus der DoD werden mit Mock-DB und Mock-HTTP-Clients
getestet. Kein echter Datenbankzugriff — alle externen Calls sind gemockt.

Szenarien:
  1. Happy Path outbound: Eintrag nach Erfolg gelöscht (kein delivered-State)
  2. Happy Path inbound: routing_state='routed' + epic_id gesetzt
  3. Retry + DLQ: nach max_attempts → sync_dead_letter + state='dead_letter'
  4. DLQ-Requeue: neuer SyncOutbox-Eintrag (attempts=0) wird verarbeitet + gelöscht
  5. pgvector-Routing Threshold: Score >= threshold → auto-assign; Score < threshold → NULL
  6. Runtime-Threshold-Change: PATCH settings → neuer Threshold wirkt sofort
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.sync import SyncDeadLetter, SyncOutbox
from app.services.outbox_consumer import (
    process_inbound,
    process_outbound,
)


# ─── Fixtures / Helpers ────────────────────────────────────────────────────


def _make_entry(
    *,
    direction: str = "outbound",
    system: str = "youtrack",
    state: str = "pending",
    routing_state: str = "unrouted",
    attempts: int = 0,
    next_retry_at=None,
    payload: dict | None = None,
) -> MagicMock:
    entry = MagicMock(spec=SyncOutbox)
    entry.id = uuid.uuid4()
    entry.direction = direction
    entry.system = system
    entry.state = state
    entry.routing_state = routing_state
    entry.attempts = attempts
    entry.next_retry_at = next_retry_at
    entry.payload = payload or {"external_id": "YT-1", "state": "in_progress"}
    entry.entity_id = "YT-1"
    entry.entity_type = "youtrack_status_sync"
    entry.target_node_id = None
    entry.raw_payload = {}
    return entry


def _make_db(entries: list) -> AsyncMock:
    """Return an AsyncMock db with the given entries for scalars().all()."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = entries

    db = AsyncMock()
    db.execute.return_value = result
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    return db


# ─── Szenario 1: Happy Path outbound ──────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_outbound_entry_is_deleted() -> None:
    """Erfolgreicher outbound Consumer-Lauf → Eintrag wird aus DB GELÖSCHT."""
    entry = _make_entry(direction="outbound", system="youtrack")
    db = _make_db([entry])

    async def _fake_dispatch(e: SyncOutbox) -> None:
        pass  # Erfolg — keine Exception

    with patch("app.services.outbox_consumer.AsyncSessionLocal", return_value=db):
        with patch("app.services.outbox_consumer._dispatch_outbound", side_effect=_fake_dispatch):
            await process_outbound()

    db.delete.assert_awaited_once_with(entry)
    db.commit.assert_awaited_once()
    # Kein state='delivered' — nur löschen
    assert entry.state == "pending"  # unverändert (weil gelöscht)


# ─── Szenario 2: Happy Path inbound ───────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_inbound_routing_state_set_to_routed() -> None:
    """Inbound-Eintrag nach Dispatch → routing_state='routed', Eintrag bleibt als Audit-Record."""
    entry = _make_entry(
        direction="inbound",
        system="sentry",
        routing_state="unrouted",
        payload={"level": "error", "title": "NullPointerException"},
    )
    db = _make_db([entry])

    routed_epic_id = uuid.uuid4()

    async def _fake_dispatch_inbound(e: SyncOutbox) -> None:
        # Simuliert SentryAggregationService + RoutingService: epic_id wird gesetzt
        e.payload["_epic_id"] = str(routed_epic_id)

    with patch("app.services.outbox_consumer.AsyncSessionLocal", return_value=db):
        with patch("app.services.outbox_consumer._dispatch_inbound", side_effect=_fake_dispatch_inbound):
            await process_inbound()

    # Eintrag wird NICHT gelöscht (bleibt als Audit-Record)
    db.delete.assert_not_awaited()
    # routing_state gesetzt
    assert entry.routing_state == "routed"
    db.commit.assert_awaited_once()


# ─── Szenario 3: Retry + DLQ-Promotion ────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_and_dlq_promotion_after_max_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nach max_attempts Fehlern → state='dead_letter' + SyncDeadLetter-Eintrag."""
    from app import config

    monkeypatch.setattr(config.settings, "hivemind_dlq_max_attempts", 5)

    entry = _make_entry(direction="outbound", system="youtrack", attempts=4)  # 5. Versuch schlägt fehl
    db = _make_db([entry])

    added_records: list = []
    db.add = MagicMock(side_effect=lambda r: added_records.append(r))

    async def _always_fail(e: SyncOutbox) -> None:
        raise RuntimeError("YouTrack: 503 Service Unavailable")

    with patch("app.services.outbox_consumer.AsyncSessionLocal", return_value=db):
        with patch("app.services.outbox_consumer._dispatch_outbound", side_effect=_always_fail):
            await process_outbound()

    # Nach 5 Fehlern: attempts = max_attempts
    assert entry.attempts == 5
    # state muss 'dead_letter' sein (kein 'dead'!)
    assert entry.state == "dead_letter"
    # Ein SyncDeadLetter-Eintrag muss erstellt worden sein
    dead_letters = [r for r in added_records if isinstance(r, SyncDeadLetter)]
    assert len(dead_letters) == 1
    assert dead_letters[0].outbox_id == entry.id
    assert "503" in dead_letters[0].error


# ─── Szenario 4: DLQ-Requeue → Consumer löscht requeueten Eintrag ─────────


@pytest.mark.asyncio
async def test_dlq_requeue_creates_new_pending_entry_with_zero_attempts() -> None:
    """Requeue eines Dead Letters → neuer Eintrag + Consumer löscht ihn erfolgreich."""
    from app.services.dlq_service import requeue_dead_letter

    dead_letter_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    dead_letter = MagicMock()
    dead_letter.id = dead_letter_id
    dead_letter.system = "youtrack"
    dead_letter.entity_type = "youtrack_status_sync"
    dead_letter.entity_id = "YT-100"
    dead_letter.payload = {"external_id": "YT-100"}
    dead_letter.requeued_at = None
    dead_letter.requeued_by = None

    source_outbox = MagicMock()
    source_outbox.direction = "outbound"
    source_outbox.target_node_id = None
    source_outbox.raw_payload = {}
    source_outbox.routing_state = "unrouted"
    source_outbox.embedding_model = None
    dead_letter.outbox_entry = source_outbox

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = dead_letter
    db = AsyncMock()
    db.execute.return_value = result_mock
    db.add = MagicMock()
    db.flush = AsyncMock()

    added: list = []
    db.add = MagicMock(side_effect=lambda r: added.append(r))

    await requeue_dead_letter(db, dead_letter_id, actor_id)

    # Es muss ein neuer SyncOutbox-Eintrag erstellt worden sein
    new_entries = [r for r in added if isinstance(r, SyncOutbox)]
    assert len(new_entries) == 1
    new = new_entries[0]
    assert new.attempts == 0
    assert new.state == "pending"
    assert new.system == "youtrack"
    assert new.next_retry_at is None

    # Dead Letter als requeued markiert
    assert dead_letter.requeued_at is not None
    assert dead_letter.requeued_by == actor_id

    # Requeue-Entry wird vom outbound-consumer verarbeitet und gelöscht
    outbound_db = _make_db([new])

    async def _dispatch_ok(e: SyncOutbox) -> None:
        pass

    with patch("app.services.outbox_consumer.AsyncSessionLocal", return_value=outbound_db):
        with patch("app.services.outbox_consumer._dispatch_outbound", side_effect=_dispatch_ok):
            await process_outbound()

    outbound_db.delete.assert_awaited_once_with(new)


# ─── Szenario 5: pgvector-Routing Threshold ────────────────────────────────


@pytest.mark.asyncio
async def test_routing_threshold_above_assigns_epic(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score >= threshold (0.90 >= 0.85) → epic_id gesetzt."""
    from app.services import routing_service

    monkeypatch.delenv("HIVEMIND_ROUTING_THRESHOLD", raising=False)
    monkeypatch.setattr(routing_service, "_threshold_cache_ts", 0.0)
    routing_service._threshold_cache.clear()

    bug_report_id = uuid.uuid4()
    epic_id = uuid.uuid4()

    # Mock: _load_threshold gibt 0.85 zurück
    # Mock: embedding
    # Mock: pgvector Query Row mit score=0.90
    mock_row = MagicMock()
    mock_row.score = 0.90
    mock_row.id = str(epic_id)

    mock_report = MagicMock()

    async def _fake_embed(text: str) -> list[float]:
        return [0.1] * 384

    with patch.object(routing_service.EMBEDDING_SVC, "embed", side_effect=_fake_embed):
        # Mock DB: threshold query + pgvector query + bug report fetch
        db = AsyncMock()
        threshold_result = MagicMock()
        threshold_result.scalar_one_or_none.return_value = None  # DB hat keinen Wert → default 0.85

        vector_result = MagicMock()
        vector_result.first.return_value = mock_row

        report_result = MagicMock()
        report_result.scalar_one_or_none.return_value = mock_report

        db.execute.side_effect = [threshold_result, vector_result, report_result]
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=db)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.routing_service.AsyncSessionLocal", return_value=session_ctx):
            result = await routing_service.route_bug_to_epic(bug_report_id, "NullPointerException in login")

    assert result.routed is True
    assert result.epic_id == epic_id
    assert result.score == pytest.approx(0.90)


@pytest.mark.asyncio
async def test_routing_threshold_below_leaves_epic_null(monkeypatch: pytest.MonkeyPatch) -> None:
    """Score < threshold (0.70 < 0.85) → epic_id bleibt NULL."""
    from app.services import routing_service

    monkeypatch.delenv("HIVEMIND_ROUTING_THRESHOLD", raising=False)
    monkeypatch.setattr(routing_service, "_threshold_cache_ts", 0.0)
    routing_service._threshold_cache.clear()

    bug_report_id = uuid.uuid4()
    epic_id = uuid.uuid4()

    mock_row = MagicMock()
    mock_row.score = 0.70
    mock_row.id = str(epic_id)

    async def _fake_embed(text: str) -> list[float]:
        return [0.1] * 384

    with patch.object(routing_service.EMBEDDING_SVC, "embed", side_effect=_fake_embed):
        db = AsyncMock()
        threshold_result = MagicMock()
        threshold_result.scalar_one_or_none.return_value = None  # default 0.85

        vector_result = MagicMock()
        vector_result.first.return_value = mock_row

        db.execute.side_effect = [threshold_result, vector_result]
        db.rollback = AsyncMock()
        db.commit = AsyncMock()

        session_ctx = AsyncMock()
        session_ctx.__aenter__ = AsyncMock(return_value=db)
        session_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.routing_service.AsyncSessionLocal", return_value=session_ctx):
            result = await routing_service.route_bug_to_epic(bug_report_id, "minor UI glitch")

    assert result.routed is False
    assert result.epic_id is None
    assert result.score == pytest.approx(0.70)
    db.rollback.assert_awaited_once()


# ─── Szenario 6: Runtime-Threshold-Change ─────────────────────────────────


@pytest.mark.asyncio
async def test_runtime_threshold_change_invalidates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nach PATCH /settings/routing-threshold: Cache wird invalidiert, neuer Wert wirkt."""
    from app.services import routing_service

    monkeypatch.delenv("HIVEMIND_ROUTING_THRESHOLD", raising=False)
    # Cache mit altem Wert befüllen
    routing_service._threshold_cache["value"] = 0.85
    routing_service._threshold_cache_ts = 9_999_999.0  # Weit in der Zukunft — würde normalerweise gecacht

    # Cache invalidieren (wie PATCH-Endpoint es macht)
    routing_service.invalidate_threshold_cache()

    assert routing_service._threshold_cache == {}
    assert routing_service._threshold_cache_ts == 0.0

    # Nächster Aufruf von _load_threshold lädt neuen Wert aus DB
    new_value_row = MagicMock()
    new_value_row.value = "0.65"

    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = new_value_row
    db.execute.return_value = result_mock

    threshold = await routing_service._load_threshold(db)

    assert threshold == pytest.approx(0.65)
    # Cache wurde neu befüllt
    assert routing_service._threshold_cache["value"] == pytest.approx(0.65)
