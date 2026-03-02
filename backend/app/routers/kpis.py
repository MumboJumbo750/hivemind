"""KPI Dashboard endpoints — TASK-7-013.

GET /api/kpis/summary — returns all 6 KPIs with value, target, status, computed_at
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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
