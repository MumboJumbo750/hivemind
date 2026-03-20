"""Integration tests for Worker Endpoint Pool strategies (TASK-AE2-002).

Tests round_robin, weighted, least_busy strategies plus
failover and recovery behavior.
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from app.services.ai_providers.pool import EndpointPool, PoolEndpoint, UNHEALTHY_COOLDOWN_SECONDS


def _pool(strategy: str = "round_robin", endpoints: list[dict] | None = None) -> EndpointPool:
    """Create a pool with 3 endpoints by default."""
    if endpoints is None:
        endpoints = [
            {"url": "http://ollama-a:11434", "weight": 1},
            {"url": "http://ollama-b:11434", "weight": 1},
            {"url": "http://ollama-c:11434", "weight": 1},
        ]
    return EndpointPool(endpoints=endpoints, strategy=strategy)


# ── Round Robin ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_round_robin_distributes_evenly() -> None:
    """TASK-AE2-002: Round robin distributes requests evenly across endpoints."""
    pool = _pool("round_robin")
    counts: dict[str, int] = {}

    for _ in range(12):
        ep = await pool.get_next_endpoint()
        assert ep is not None
        counts[ep.url] = counts.get(ep.url, 0) + 1

    # Each endpoint should get exactly 4 requests
    assert counts["http://ollama-a:11434"] == 4
    assert counts["http://ollama-b:11434"] == 4
    assert counts["http://ollama-c:11434"] == 4


@pytest.mark.asyncio
async def test_round_robin_cycles_correctly() -> None:
    """TASK-AE2-002: Round robin cycles A → B → C → A → ..."""
    pool = _pool("round_robin")
    urls = []
    for _ in range(6):
        ep = await pool.get_next_endpoint()
        assert ep is not None
        urls.append(ep.url)

    expected = [
        "http://ollama-a:11434",
        "http://ollama-b:11434",
        "http://ollama-c:11434",
    ] * 2
    assert urls == expected


# ── Weighted ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weighted_distribution_matches_weights() -> None:
    """TASK-AE2-002: Weighted strategy distributes proportional to weights ±10%."""
    pool = _pool("weighted", endpoints=[
        {"url": "http://ollama-a:11434", "weight": 3},
        {"url": "http://ollama-b:11434", "weight": 1},
    ])
    counts: dict[str, int] = {}
    n = 400  # large enough for statistical stability

    for _ in range(n):
        ep = await pool.get_next_endpoint()
        assert ep is not None
        counts[ep.url] = counts.get(ep.url, 0) + 1

    ratio_a = counts.get("http://ollama-a:11434", 0) / n
    ratio_b = counts.get("http://ollama-b:11434", 0) / n

    # Expected: A=75%, B=25% — allow ±10%
    assert 0.65 <= ratio_a <= 0.85, f"Expected A ~75%, got {ratio_a:.1%}"
    assert 0.15 <= ratio_b <= 0.35, f"Expected B ~25%, got {ratio_b:.1%}"


# ── Failover ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failover_skips_unhealthy_endpoint() -> None:
    """TASK-AE2-002: Unhealthy endpoint is skipped in selection."""
    pool = _pool("round_robin", endpoints=[
        {"url": "http://ollama-a:11434"},
        {"url": "http://ollama-b:11434"},
    ])

    await pool.mark_unhealthy("http://ollama-b:11434")

    for _ in range(5):
        ep = await pool.get_next_endpoint()
        assert ep is not None
        assert ep.url == "http://ollama-a:11434", "Unhealthy endpoint should be skipped"


@pytest.mark.asyncio
async def test_failover_all_unhealthy_returns_none() -> None:
    """TASK-AE2-002: All endpoints unhealthy (within cooldown) returns None."""
    pool = _pool("round_robin", endpoints=[
        {"url": "http://ollama-a:11434"},
        {"url": "http://ollama-b:11434"},
    ])

    await pool.mark_unhealthy("http://ollama-a:11434")
    await pool.mark_unhealthy("http://ollama-b:11434")

    ep = await pool.get_next_endpoint()
    assert ep is None, "Should return None when all endpoints unhealthy within cooldown"


# ── Recovery ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recovery_after_cooldown() -> None:
    """TASK-AE2-002: Unhealthy endpoint recovers after cooldown period."""
    pool = _pool("round_robin", endpoints=[
        {"url": "http://ollama-a:11434"},
        {"url": "http://ollama-b:11434"},
    ])

    await pool.mark_unhealthy("http://ollama-a:11434")
    await pool.mark_unhealthy("http://ollama-b:11434")

    # Simulate cooldown expiry by backdating last_health_check
    for ep in pool._endpoints:
        ep.last_health_check = time.monotonic() - UNHEALTHY_COOLDOWN_SECONDS - 1

    ep = await pool.get_next_endpoint()
    assert ep is not None, "Endpoints should recover after cooldown"
    assert ep.healthy is True, "Recovered endpoint should be marked healthy"


@pytest.mark.asyncio
async def test_recovery_partial_cooldown() -> None:
    """TASK-AE2-002: Only expired endpoints recover, others stay unhealthy."""
    pool = _pool("round_robin", endpoints=[
        {"url": "http://ollama-a:11434"},
        {"url": "http://ollama-b:11434"},
    ])

    await pool.mark_unhealthy("http://ollama-a:11434")
    await pool.mark_unhealthy("http://ollama-b:11434")

    # Only A has expired cooldown
    pool._endpoints[0].last_health_check = time.monotonic() - UNHEALTHY_COOLDOWN_SECONDS - 1

    ep = await pool.get_next_endpoint()
    assert ep is not None
    assert ep.url == "http://ollama-a:11434", "Only cooled-down endpoint should recover"


# ── Least Busy ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_least_busy_selects_least_loaded() -> None:
    """TASK-AE2-002: Least busy strategy selects endpoint with fewest active dispatches."""
    pool = _pool("least_busy", endpoints=[
        {"url": "http://ollama-a:11434"},
        {"url": "http://ollama-b:11434"},
        {"url": "http://ollama-c:11434"},
    ])

    # Simulate load: A=3, B=1, C=0
    pool._endpoints[0].active_dispatches = 3
    pool._endpoints[1].active_dispatches = 1
    pool._endpoints[2].active_dispatches = 0

    ep = await pool.get_next_endpoint()
    assert ep is not None
    assert ep.url == "http://ollama-c:11434", "Should select least busy endpoint (C with 0 dispatches)"


@pytest.mark.asyncio
async def test_least_busy_skips_unhealthy() -> None:
    """TASK-AE2-002: Least busy skips unhealthy even if least loaded."""
    pool = _pool("least_busy", endpoints=[
        {"url": "http://ollama-a:11434"},
        {"url": "http://ollama-b:11434"},
    ])

    pool._endpoints[0].active_dispatches = 5
    pool._endpoints[1].active_dispatches = 0
    await pool.mark_unhealthy("http://ollama-b:11434")

    ep = await pool.get_next_endpoint()
    assert ep is not None
    assert ep.url == "http://ollama-a:11434", "Should skip unhealthy B even though less busy"


# ── Metrics ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_call_updates_metrics() -> None:
    """TASK-AE2-002: record_call updates total_calls and response time metrics."""
    pool = _pool("round_robin", endpoints=[{"url": "http://ollama-a:11434"}])

    await pool.record_call("http://ollama-a:11434", 150)
    await pool.record_call("http://ollama-a:11434", 250)

    ep = pool._endpoints[0]
    assert ep.total_calls == 2
    assert ep.total_response_time_ms == 400
    assert ep.avg_response_ms == 200.0


def test_pool_status_returns_all_endpoints() -> None:
    """TASK-AE2-002: get_status returns metrics for all endpoints."""
    pool = _pool("round_robin")
    status = pool.get_status()

    assert len(status) == 3
    assert all("url" in s and "healthy" in s and "weight" in s for s in status)
