"""Tests for EmbeddingService with circuit-breaker and provider abstraction."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.embedding_service import (
    CBState,
    CircuitBreaker,
    EMBEDDING_TEXT_COLS,
    EmbeddingJob,
    EmbeddingPriority,
    EmbeddingProvider,
    EmbeddingService,
    OllamaProvider,
)


# ── Fake provider ────────────────────────────────────────────────────────────


class FakeProvider(EmbeddingProvider):
    def __init__(self, dim: int = 768):
        self.dim = dim
        self.call_count = 0
        self.fail_after: int | None = None  # fail after N calls

    async def embed(self, text_input: str) -> list[float]:
        self.call_count += 1
        if self.fail_after is not None and self.call_count > self.fail_after:
            raise TimeoutError("Ollama timeout")
        return [0.1] * self.dim

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


class _SessionCtx:
    def __init__(self, db: AsyncMock) -> None:
        self._db = db

    async def __aenter__(self) -> AsyncMock:
        return self._db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


# ── Provider tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fake_provider_embed():
    provider = FakeProvider()
    result = await provider.embed("hello")
    assert len(result) == 768
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_fake_provider_batch():
    provider = FakeProvider()
    results = await provider.embed_batch(["a", "b", "c"])
    assert len(results) == 3
    assert all(len(r) == 768 for r in results)


@pytest.mark.asyncio
async def test_fake_provider_failure():
    provider = FakeProvider()
    provider.fail_after = 0  # fail immediately
    with pytest.raises(TimeoutError):
        await provider.embed("fail")


# ── Circuit-Breaker tests ───────────────────────────────────────────────────


def test_cb_initial_state():
    cb = CircuitBreaker(threshold=3, backoff_base=60, backoff_max=600)
    assert cb.state == CBState.CLOSED
    assert cb.consecutive_failures == 0
    assert cb.allow_request() is True


def test_cb_stays_closed_under_threshold():
    cb = CircuitBreaker(threshold=3, backoff_base=60, backoff_max=600)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CBState.CLOSED
    assert cb.allow_request() is True


def test_cb_opens_at_threshold():
    cb = CircuitBreaker(threshold=3, backoff_base=60, backoff_max=600)
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CBState.OPEN
    assert cb.allow_request() is False


def test_cb_half_open_after_backoff():
    cb = CircuitBreaker(threshold=3, backoff_base=60, backoff_max=600)
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CBState.OPEN

    # Simulate time passing beyond backoff
    cb.last_failure_time = time.monotonic() - 70
    assert cb.allow_request() is True
    assert cb.state == CBState.HALF_OPEN


def test_cb_half_open_success_closes():
    cb = CircuitBreaker(threshold=3, backoff_base=60, backoff_max=600)
    for _ in range(3):
        cb.record_failure()
    cb.last_failure_time = time.monotonic() - 70
    cb.allow_request()  # transitions to HALF_OPEN
    assert cb.state == CBState.HALF_OPEN

    cb.record_success()
    assert cb.state == CBState.CLOSED
    assert cb.consecutive_failures == 0


def test_cb_half_open_failure_reopens():
    cb = CircuitBreaker(threshold=3, backoff_base=60, backoff_max=600)
    for _ in range(3):
        cb.record_failure()
    cb.last_failure_time = time.monotonic() - 70
    cb.allow_request()  # transitions to HALF_OPEN

    cb.record_failure()
    assert cb.state == CBState.OPEN
    assert cb.backoff_multiplier == 1  # increased from 0


def test_cb_adaptive_backoff():
    cb = CircuitBreaker(threshold=3, backoff_base=60, backoff_max=600)
    # Open circuit
    for _ in range(3):
        cb.record_failure()

    # First backoff = 60s
    assert cb._current_backoff() == 60

    # Simulate half-open + fail → backoff doubles
    cb.last_failure_time = time.monotonic() - 70
    cb.allow_request()
    cb.record_failure()
    assert cb._current_backoff() == 120

    # Again → 240
    cb.last_failure_time = time.monotonic() - 130
    cb.allow_request()
    cb.record_failure()
    assert cb._current_backoff() == 240

    # Again → 480
    cb.last_failure_time = time.monotonic() - 250
    cb.allow_request()
    cb.record_failure()
    assert cb._current_backoff() == 480

    # Max cap at 600
    cb.last_failure_time = time.monotonic() - 490
    cb.allow_request()
    cb.record_failure()
    assert cb._current_backoff() == 600


def test_cb_backoff_reset_after_stable_closed():
    cb = CircuitBreaker(
        threshold=3, backoff_base=60, backoff_max=600, reset_window=600.0
    )
    # Open → half-open → fail (increase multiplier)
    for _ in range(3):
        cb.record_failure()
    cb.last_failure_time = time.monotonic() - 70
    cb.allow_request()
    cb.record_failure()
    assert cb.backoff_multiplier == 1

    # Half-open → success → CLOSED
    cb.last_failure_time = time.monotonic() - 130
    cb.allow_request()
    cb.record_success()
    assert cb.state == CBState.CLOSED

    # Simulate 10 min stable
    cb._closed_since = time.monotonic() - 610
    cb.record_success()
    assert cb.backoff_multiplier == 0  # reset


# ── Service-level tests ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_service_embed_success():
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    result = await svc.embed("hello world")
    assert result is not None
    assert len(result) == 768


@pytest.mark.asyncio
async def test_service_embed_failure_returns_none():
    provider = FakeProvider()
    provider.fail_after = 0
    svc = EmbeddingService(provider=provider)
    result = await svc.embed("fail")
    assert result is None


@pytest.mark.asyncio
async def test_service_circuit_breaker_opens():
    provider = FakeProvider()
    provider.fail_after = 0
    svc = EmbeddingService(provider=provider)

    # Trigger threshold (3) failures
    for _ in range(3):
        result = await svc.embed("fail")
        assert result is None

    assert svc.circuit_breaker.state == CBState.OPEN

    # Next call should not even reach the provider
    call_count_before = provider.call_count
    result = await svc.embed("should skip")
    assert result is None
    assert provider.call_count == call_count_before  # no new call


@pytest.mark.asyncio
async def test_service_batch_embed():
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    results = await svc.embed_batch(["a", "b"])
    assert len(results) == 2
    assert all(r is not None and len(r) == 768 for r in results)


@pytest.mark.asyncio
async def test_service_batch_failure_returns_nones():
    provider = FakeProvider()
    provider.fail_after = 0
    svc = EmbeddingService(provider=provider)
    results = await svc.embed_batch(["a", "b"])
    assert all(r is None for r in results)


@pytest.mark.asyncio
async def test_search_similar_returns_empty_for_explicit_empty_candidate_ids():
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    svc.embed_query = AsyncMock(return_value=[0.1] * 768)
    db = AsyncMock()

    result = await svc.search_similar(
        db,
        'memory_entries',
        'semantic query',
        limit=5,
        candidate_ids=[],
    )

    assert result == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_service_null_embedding_feature_degradation():
    """NULL-embedding = feature degradation, not an error."""
    provider = FakeProvider()
    provider.fail_after = 0
    svc = EmbeddingService(provider=provider)

    # Should return None, not raise
    result = await svc.embed("anything")
    assert result is None

    # Batch too
    results = await svc.embed_batch(["x", "y"])
    assert results == [None, None]


@pytest.mark.asyncio
async def test_service_enqueue():
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    await svc.enqueue("skills", "abc-123", "some text", EmbeddingPriority.ON_WRITE)
    assert svc._queue.qsize() == 1


@pytest.mark.asyncio
async def test_service_enqueue_rejects_unknown_table():
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    with pytest.raises(ValueError, match="Unsupported embedding table"):
        await svc.enqueue("unknown_table", "abc-123", "some text", EmbeddingPriority.ON_WRITE)


@pytest.mark.asyncio
async def test_priority_ordering():
    """Jobs with higher priority (lower int) should be dequeued first."""
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    available_at = time.monotonic()

    await svc.enqueue("skills", "1", "text", EmbeddingPriority.FEDERATION, available_at=available_at)
    await svc.enqueue("skills", "2", "text", EmbeddingPriority.ON_WRITE, available_at=available_at)
    await svc.enqueue("skills", "3", "text", EmbeddingPriority.BATCH, available_at=available_at)

    job1 = await svc._queue.get()
    job2 = await svc._queue.get()
    job3 = await svc._queue.get()

    assert job1.priority == EmbeddingPriority.ON_WRITE
    assert job2.priority == EmbeddingPriority.BATCH
    assert job3.priority == EmbeddingPriority.FEDERATION


@pytest.mark.asyncio
async def test_ollama_provider_interface():
    """OllamaProvider implements EmbeddingProvider interface."""
    provider = OllamaProvider()
    assert isinstance(provider, EmbeddingProvider)
    assert hasattr(provider, "embed")
    assert hasattr(provider, "embed_batch")


@pytest.mark.asyncio
async def test_search_similar_passes_candidate_filter() -> None:
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    db = AsyncMock()
    row = MagicMock()
    row.id = "skill-1"
    row.similarity = 0.91
    db.execute = AsyncMock(return_value=[row])

    results = await svc.search_similar(
        db,
        "skills",
        "jwt auth",
        limit=3,
        candidate_ids=["skill-1", "skill-2"],
    )

    assert results == [{"id": "skill-1", "similarity": 0.91}]
    stmt = db.execute.await_args.args[0]
    params = db.execute.await_args.args[1]
    assert "id::text IN" in str(stmt)
    assert params["candidate_ids"] == ["skill-1", "skill-2"]


@pytest.mark.asyncio
async def test_embed_query_uses_cache() -> None:
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)

    first = await svc.embed_query("jwt auth")
    second = await svc.embed_query("jwt auth")

    assert first == second
    assert provider.call_count == 1


@pytest.mark.asyncio
async def test_process_job_requeues_when_embedding_unavailable() -> None:
    provider = FakeProvider()
    provider.fail_after = 0
    svc = EmbeddingService(provider=provider)
    db = AsyncMock()
    job = EmbeddingJob(
        available_at=time.monotonic(),
        priority=EmbeddingPriority.ON_WRITE,
        table="skills",
        record_id="skill-1",
        text="jwt auth",
    )

    await svc._process_job(db, job)

    assert svc._queue.qsize() == 1
    retried = await svc._queue.get()
    assert retried.table == "skills"
    assert retried.record_id == "skill-1"
    assert retried.attempts == 1
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_enqueue_missing_embeddings_scans_supported_tables() -> None:
    provider = FakeProvider()
    svc = EmbeddingService(provider=provider)
    db = AsyncMock()

    db.execute = AsyncMock(
        side_effect=[
            MagicMock(all=MagicMock(return_value=[SimpleNamespace(id="epic-1", txt="epic text")])),
            MagicMock(all=MagicMock(return_value=[SimpleNamespace(id="doc-1", txt="doc text")])),
        ]
    )

    with patch("app.db.AsyncSessionLocal", new=lambda: _SessionCtx(db)):
        counts = await svc.enqueue_missing_embeddings(tables=["epics", "docs"], limit_per_table=10)

    assert counts == {"epics": 1, "docs": 1}
    assert svc._queue.qsize() == 2
    assert set(["epics", "docs"]).issubset(EMBEDDING_TEXT_COLS.keys())
