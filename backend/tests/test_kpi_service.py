"""Unit tests for KPI cache service (TASK-7-013)."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.services import kpi_service


def _kpi_item(name: str) -> dict:
    return {
        "kpi": name,
        "value": 1.0,
        "target": 1.0,
        "status": "ok",
        "computed_at": datetime.now(UTC).isoformat(),
    }


@pytest.mark.asyncio
async def test_refresh_kpi_cache_sets_cache_and_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kpi_service._kpi_cache = []
    kpi_service._computed_at = None
    monkeypatch.setattr(
        kpi_service,
        "compute_kpis",
        AsyncMock(return_value=[_kpi_item(f"k{i}") for i in range(6)]),
    )

    ok = await kpi_service.refresh_kpi_cache()

    assert ok is True
    assert len(kpi_service._kpi_cache) == 6
    assert kpi_service._computed_at is not None


@pytest.mark.asyncio
async def test_refresh_kpi_cache_rejects_incomplete_kpi_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous_ts = datetime(2026, 1, 1, tzinfo=UTC)
    previous_cache = [_kpi_item("existing")]
    kpi_service._kpi_cache = previous_cache.copy()
    kpi_service._computed_at = previous_ts
    monkeypatch.setattr(
        kpi_service,
        "compute_kpis",
        AsyncMock(return_value=[_kpi_item(f"k{i}") for i in range(5)]),
    )

    ok = await kpi_service.refresh_kpi_cache()

    assert ok is False
    assert kpi_service._computed_at == previous_ts
    assert kpi_service._kpi_cache == previous_cache


@pytest.mark.asyncio
async def test_get_or_compute_kpis_raises_when_initial_refresh_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kpi_service._kpi_cache = []
    kpi_service._computed_at = None
    monkeypatch.setattr(
        kpi_service,
        "refresh_kpi_cache",
        AsyncMock(return_value=False),
    )

    with pytest.raises(RuntimeError, match="KPI cache is unavailable"):
        await kpi_service.get_or_compute_kpis()
