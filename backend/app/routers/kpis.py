"""KPI Dashboard endpoints — TASK-7-013 / TASK-8-026.

GET /api/kpis/summary — returns all 6 KPIs with value, target, status, computed_at
GET /api/kpis/history — returns per-day time series for the past N days
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.services.kpi_service import get_or_compute_kpis

router = APIRouter(prefix="/kpis", tags=["kpis"])


class KpiItem(BaseModel):
    kpi: str
    value: float
    target: float
    status: Literal["ok", "warn", "critical"]
    computed_at: str


class KpiSummaryResponse(BaseModel):
    kpis: list[KpiItem]
    computed_at: Optional[str] = None


@router.get("/summary", response_model=KpiSummaryResponse)
async def get_kpi_summary(
    actor: CurrentActor = Depends(get_current_actor),
) -> KpiSummaryResponse:
    del actor
    try:
        kpis_raw, computed_at = await get_or_compute_kpis()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    items = [KpiItem(**k) for k in kpis_raw]
    return KpiSummaryResponse(
        kpis=items,
        computed_at=computed_at.isoformat() if computed_at else None,
    )


# ── KPI History endpoint (TASK-8-026) ─────────────────────────────────────────


class KpiDataPoint(BaseModel):
    date: str    # ISO date string YYYY-MM-DD
    value: float


class KpiHistoryResponse(BaseModel):
    days: int
    series: dict[str, list[KpiDataPoint]]


def _zero_series(day_labels: list[str]) -> list[KpiDataPoint]:
    """Return a list of zero-value data points for all given day labels."""
    return [KpiDataPoint(date=d, value=0.0) for d in day_labels]


@router.get("/history", response_model=KpiHistoryResponse)
async def get_kpi_history(
    days: int = Query(7, ge=1, le=90, description="Number of past days to return"),
    actor: CurrentActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> KpiHistoryResponse:
    """Return per-day time series for the past N days (TASK-8-026).

    Metrics backed by real DB data:
      - tasks_done          — tasks that transitioned to 'done' each day
      - tasks_in_progress   — tasks in 'in_progress' state created/updated that day

    Metrics not yet tracked historically return zero series.
    """
    del actor

    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(days=days)

    # Build ordered list of date labels (oldest → newest)
    day_labels: list[str] = [
        (cutoff + timedelta(days=i + 1)).date().isoformat()
        for i in range(days)
    ]

    # ── tasks_done per day ────────────────────────────────────────────────────
    done_result = await db.execute(
        text(
            "SELECT DATE(updated_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS cnt "
            "FROM tasks "
            "WHERE state = 'done' "
            "  AND updated_at >= :cutoff "
            "GROUP BY day "
            "ORDER BY day"
        ),
        {"cutoff": cutoff},
    )
    done_by_day: dict[str, float] = {
        str(row.day): float(row.cnt) for row in done_result.all()
    }

    # ── tasks_in_progress per day ─────────────────────────────────────────────
    ip_result = await db.execute(
        text(
            "SELECT DATE(updated_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS cnt "
            "FROM tasks "
            "WHERE state = 'in_progress' "
            "  AND updated_at >= :cutoff "
            "GROUP BY day "
            "ORDER BY day"
        ),
        {"cutoff": cutoff},
    )
    ip_by_day: dict[str, float] = {
        str(row.day): float(row.cnt) for row in ip_result.all()
    }

    def _build(lookup: dict[str, float]) -> list[KpiDataPoint]:
        return [KpiDataPoint(date=d, value=lookup.get(d, 0.0)) for d in day_labels]

    return KpiHistoryResponse(
        days=days,
        series={
            "tasks_done": _build(done_by_day),
            "tasks_in_progress": _build(ip_by_day),
            # The following metrics are not yet tracked per-day in the DB;
            # return zero series so the frontend can render placeholders.
            "cycle_time_avg_hours": _zero_series(day_labels),
            "bug_rate": _zero_series(day_labels),
            "skill_coverage": _zero_series(day_labels),
            "review_pass_rate": _zero_series(day_labels),
        },
    )
