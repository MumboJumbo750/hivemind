"""API tests for KPI summary endpoint (TASK-7-013)."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest


def _kpi_item(name: str) -> dict:
    return {
        "kpi": name,
        "value": 1.0,
        "target": 1.0,
        "status": "ok",
        "computed_at": "2026-03-01T12:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_get_kpi_summary_returns_six_kpis(client) -> None:
    computed_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    mocked = ([_kpi_item(f"k{i}") for i in range(6)], computed_at)

    with patch("app.routers.kpis.get_or_compute_kpis", AsyncMock(return_value=mocked)):
        response = await client.get("/api/kpis/summary")

    assert response.status_code == 200
    body = response.json()
    assert len(body["kpis"]) == 6
    assert body["computed_at"] == computed_at.isoformat()


@pytest.mark.asyncio
async def test_get_kpi_summary_returns_503_when_cache_unavailable(client) -> None:
    with patch(
        "app.routers.kpis.get_or_compute_kpis",
        AsyncMock(side_effect=RuntimeError("KPI cache is unavailable")),
    ):
        response = await client.get("/api/kpis/summary")

    assert response.status_code == 503
    assert response.json()["detail"] == "KPI cache is unavailable"
