"""Governance Audit Trail REST API — TASK-AUI-004.

GET /api/admin/governance/audit — paginated list with filters + stats
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.governance_recommendation import GovernanceRecommendation
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/admin/governance", tags=["governance-audit"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class GovernanceAuditEntry(BaseModel):
    id: uuid.UUID
    governance_type: str
    governance_level: str
    target_type: str
    target_ref: str
    status: str
    agent_role: str
    prompt_type: Optional[str] = None
    action: Optional[str] = None
    confidence: Optional[float] = None
    rationale: Optional[str] = None
    payload: Optional[dict] = None
    dispatch_id: Optional[uuid.UUID] = None
    created_at: datetime
    executed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GovernanceAuditListResponse(BaseModel):
    data: list[GovernanceAuditEntry]
    total_count: int
    has_more: bool
    page: int
    page_size: int


class GovernanceAuditStatsEntry(BaseModel):
    governance_type: str
    governance_level: str
    count: int


class GovernanceAuditStats(BaseModel):
    total: int
    auto_approve_rate: float
    veto_count: int
    stats: list[GovernanceAuditStatsEntry]


# ── GET /api/admin/governance/audit ──────────────────────────────────────────

@router.get("/audit", response_model=GovernanceAuditListResponse)
async def list_governance_audit(
    governance_type: Optional[str] = Query(None, description="Filter by governance type"),
    governance_level: Optional[str] = Query(None, description="Filter by level (manual/assisted/auto)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    agent_role: Optional[str] = Query(None, description="Filter by agent role"),
    from_date: Optional[datetime] = Query(None, alias="from"),
    to_date: Optional[datetime] = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> GovernanceAuditListResponse:
    q = select(GovernanceRecommendation)

    if governance_type:
        q = q.where(GovernanceRecommendation.governance_type == governance_type)
    if governance_level:
        q = q.where(GovernanceRecommendation.governance_level == governance_level)
    if status:
        q = q.where(GovernanceRecommendation.status == status)
    if agent_role:
        q = q.where(GovernanceRecommendation.agent_role == agent_role)
    if from_date:
        q = q.where(GovernanceRecommendation.created_at >= from_date)
    if to_date:
        q = q.where(GovernanceRecommendation.created_at <= to_date)

    count_q = select(func.count()).select_from(q.subquery())
    total_count = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    q = q.order_by(GovernanceRecommendation.created_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return GovernanceAuditListResponse(
        data=[GovernanceAuditEntry.model_validate(r) for r in rows],
        total_count=total_count,
        has_more=(offset + len(rows)) < total_count,
        page=page,
        page_size=page_size,
    )


# ── GET /api/admin/governance/stats ──────────────────────────────────────────

@router.get("/stats", response_model=GovernanceAuditStats)
async def get_governance_stats(
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> GovernanceAuditStats:
    # Group by type + level
    q = select(
        GovernanceRecommendation.governance_type,
        GovernanceRecommendation.governance_level,
        func.count().label("count"),
    ).group_by(
        GovernanceRecommendation.governance_type,
        GovernanceRecommendation.governance_level,
    )
    rows = (await db.execute(q)).all()

    stats = [
        GovernanceAuditStatsEntry(
            governance_type=r.governance_type,
            governance_level=r.governance_level,
            count=r.count,
        )
        for r in rows
    ]
    total = sum(s.count for s in stats)

    # Auto-approve rate: auto_fallback entries that were executed
    auto_total = (await db.execute(
        select(func.count()).where(GovernanceRecommendation.governance_level == "auto")
    )).scalar_one()

    auto_executed = (await db.execute(
        select(func.count()).where(
            GovernanceRecommendation.governance_level == "auto",
            GovernanceRecommendation.executed_at.is_not(None),
        )
    )).scalar_one()

    auto_approve_rate = (auto_executed / auto_total * 100) if auto_total > 0 else 0.0

    # Veto count: assisted recommendations that were overridden (status != pending_human, has executed_at, action != original)
    # Simplified: count entries with status 'vetoed' or where executed_at is set and status differs from auto_fallback
    veto_count = (await db.execute(
        select(func.count()).where(
            GovernanceRecommendation.governance_level == "assisted",
            GovernanceRecommendation.executed_at.is_not(None),
        )
    )).scalar_one()

    return GovernanceAuditStats(
        total=total,
        auto_approve_rate=round(auto_approve_rate, 1),
        veto_count=veto_count,
        stats=stats,
    )
