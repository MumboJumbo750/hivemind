"""KPI Dashboard endpoints — TASK-7-013 / TASK-8-026.

GET /api/kpis/summary — returns all 6 KPIs with value, target, status, computed_at
GET /api/kpis/history — returns per-day time series for the past N days
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.conductor import ConductorDispatch
from app.models.governance_recommendation import GovernanceRecommendation
from app.models.learning_artifact import LearningArtifact
from app.models.review import ReviewRecommendation
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.services.kpi_service import get_or_compute_kpis
from app.services.learning_artifacts import list_execution_learning_artifacts

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


class AgentLoopSummaryResponse(BaseModel):
    window_days: int
    dispatch_success_rate: float
    average_handoff_seconds: float
    review_auto_approval_rate: float
    pending_governance_recommendations: int
    learning_artifacts_created: int
    suppressed_learning_artifacts: int
    series: dict[str, list[KpiDataPoint]]


class ExecutionLearningItem(BaseModel):
    id: str
    summary: str
    status: str
    confidence: float | None = None
    kind: str | None = None
    audiences: list[str] = []
    occurrence_count: int = 0
    prompt_inclusions: int = 0
    success_count: int = 0
    qa_failed_count: int = 0
    created_at: str


class ExecutionLearningListResponse(BaseModel):
    items: list[ExecutionLearningItem]


def _zero_series(day_labels: list[str]) -> list[KpiDataPoint]:
    """Return a list of zero-value data points for all given day labels."""
    return [KpiDataPoint(date=d, value=0.0) for d in day_labels]


@router.get("/execution-learnings", response_model=ExecutionLearningListResponse)
async def get_execution_learnings(
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    audience: str | None = Query(None),
    actor: CurrentActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> ExecutionLearningListResponse:
    del actor
    artifacts = await list_execution_learning_artifacts(
        db,
        limit=limit,
        status=status,
        audience=audience,
    )
    items = []
    for artifact in artifacts:
        detail = dict(artifact.detail or {})
        effectiveness = dict(detail.get("effectiveness") or {})
        items.append(
            ExecutionLearningItem(
                id=str(artifact.id),
                summary=artifact.summary,
                status=artifact.status,
                confidence=artifact.confidence,
                kind=detail.get("kind"),
                audiences=list(detail.get("audiences") or []),
                occurrence_count=int(detail.get("occurrence_count") or 0),
                prompt_inclusions=int(effectiveness.get("prompt_inclusions") or 0),
                success_count=int(effectiveness.get("success_count") or 0),
                qa_failed_count=int(effectiveness.get("qa_failed_count") or 0),
                created_at=artifact.created_at.isoformat(),
            )
        )
    return ExecutionLearningListResponse(items=items)


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


@router.get("/agent-loop", response_model=AgentLoopSummaryResponse)
async def get_agent_loop_summary(
    days: int = Query(14, ge=1, le=90, description="Number of past days to analyze"),
    actor: CurrentActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> AgentLoopSummaryResponse:
    del actor

    now_utc = datetime.now(UTC)
    cutoff = now_utc - timedelta(days=days)
    day_labels = [
        (cutoff + timedelta(days=i + 1)).date().isoformat()
        for i in range(days)
    ]

    dispatch_stats = (
        await db.execute(
            select(
                func.count(ConductorDispatch.id),
                func.count(ConductorDispatch.id).filter(
                    ConductorDispatch.status.in_(["completed", "partial"])
                ),
                func.avg(
                    func.extract(
                        "epoch",
                        ConductorDispatch.completed_at - ConductorDispatch.dispatched_at,
                    )
                ),
            ).where(ConductorDispatch.dispatched_at >= cutoff)
        )
    ).one()
    total_dispatches = int(dispatch_stats[0] or 0)
    successful_dispatches = int(dispatch_stats[1] or 0)
    avg_handoff = round(float(dispatch_stats[2] or 0.0), 1)

    review_stats = (
        await db.execute(
            select(
                func.count(ReviewRecommendation.id),
                func.count(ReviewRecommendation.id).filter(
                    ReviewRecommendation.auto_approved.is_(True)
                ),
            ).where(ReviewRecommendation.created_at >= cutoff)
        )
    ).one()
    total_reviews = int(review_stats[0] or 0)
    auto_reviews = int(review_stats[1] or 0)

    pending_governance = (
        await db.execute(
            select(func.count(GovernanceRecommendation.id)).where(
                GovernanceRecommendation.status.in_(["pending_human", "auto_fallback"])
            )
        )
    ).scalar_one()

    learning_stats = (
        await db.execute(
            select(
                func.count(LearningArtifact.id),
                func.count(LearningArtifact.id).filter(LearningArtifact.status == "suppressed"),
            ).where(LearningArtifact.created_at >= cutoff)
        )
    ).one()
    learning_total = int(learning_stats[0] or 0)
    learning_suppressed = int(learning_stats[1] or 0)

    dispatch_day_rows = (
        await db.execute(
            text(
                "SELECT DATE(dispatched_at AT TIME ZONE 'UTC') AS day, "
                "COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE status IN ('completed', 'partial')) AS ok "
                "FROM conductor_dispatches "
                "WHERE dispatched_at >= :cutoff "
                "GROUP BY day ORDER BY day"
            ),
            {"cutoff": cutoff},
        )
    ).all()
    dispatch_ok_lookup = {str(row.day): float(row.ok) for row in dispatch_day_rows}
    dispatch_total_lookup = {str(row.day): float(row.total) for row in dispatch_day_rows}

    learning_day_rows = (
        await db.execute(
            text(
                "SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS total "
                "FROM learning_artifacts "
                "WHERE created_at >= :cutoff "
                "GROUP BY day ORDER BY day"
            ),
            {"cutoff": cutoff},
        )
    ).all()
    learning_lookup = {str(row.day): float(row.total) for row in learning_day_rows}

    governance_day_rows = (
        await db.execute(
            text(
                "SELECT DATE(created_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS total "
                "FROM governance_recommendations "
                "WHERE created_at >= :cutoff "
                "GROUP BY day ORDER BY day"
            ),
            {"cutoff": cutoff},
        )
    ).all()
    governance_lookup = {str(row.day): float(row.total) for row in governance_day_rows}

    def _build(lookup: dict[str, float]) -> list[KpiDataPoint]:
        return [KpiDataPoint(date=day, value=lookup.get(day, 0.0)) for day in day_labels]

    return AgentLoopSummaryResponse(
        window_days=days,
        dispatch_success_rate=round((successful_dispatches / total_dispatches * 100.0) if total_dispatches else 100.0, 1),
        average_handoff_seconds=avg_handoff,
        review_auto_approval_rate=round((auto_reviews / total_reviews * 100.0) if total_reviews else 0.0, 1),
        pending_governance_recommendations=int(pending_governance or 0),
        learning_artifacts_created=learning_total,
        suppressed_learning_artifacts=learning_suppressed,
        series={
            "dispatch_completed": _build(dispatch_ok_lookup),
            "dispatch_total": _build(dispatch_total_lookup),
            "learning_artifacts": _build(learning_lookup),
            "governance_recommendations": _build(governance_lookup),
        },
    )
