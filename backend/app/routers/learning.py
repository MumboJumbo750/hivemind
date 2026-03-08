"""Learning Artifacts REST API — TASK-AGENT-004.

GET /api/learning/artifacts       — paginierte Liste mit Filtern
GET /api/learning/artifacts/{id}  — Einzel-Artefakt
GET /api/learning/stats           — Aggregate nach Typ/Status
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.learning_artifact import LearningArtifact
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/learning", tags=["learning"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class LearningArtifactResponse(BaseModel):
    id: uuid.UUID
    artifact_type: str
    status: str
    source_type: str
    source_ref: str
    source_dispatch_id: Optional[uuid.UUID] = None
    agent_role: Optional[str] = None
    project_id: Optional[uuid.UUID] = None
    epic_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    summary: str
    detail: Optional[dict] = None
    confidence: Optional[float] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class LearningListResponse(BaseModel):
    data: list[LearningArtifactResponse]
    total_count: int
    has_more: bool
    page: int
    page_size: int


class LearningStatsEntry(BaseModel):
    artifact_type: str
    status: str
    count: int


class LearningStatsResponse(BaseModel):
    stats: list[LearningStatsEntry]
    total: int
    skill_candidates: int


# ── GET /api/learning/artifacts ───────────────────────────────────────────────

@router.get("/artifacts", response_model=LearningListResponse)
async def list_learning_artifacts(
    artifact_type: Optional[str] = Query(None, description="Typ-Filter (agent_output | review_feedback | governance_recommendation | execution_learning)"),
    status: Optional[str] = Query(None, description="Status-Filter (observation | proposal | suppressed)"),
    agent_role: Optional[str] = Query(None, description="Rollen-Filter (worker | reviewer | gaertner | triage | stratege | architekt)"),
    source_type: Optional[str] = Query(None, description="Quell-Typ-Filter"),
    task_id: Optional[uuid.UUID] = Query(None, description="Filter nach Task-UUID"),
    epic_id: Optional[uuid.UUID] = Query(None, description="Filter nach Epic-UUID"),
    project_id: Optional[uuid.UUID] = Query(None, description="Filter nach Projekt-UUID"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Mindestkonfidenz"),
    from_date: Optional[datetime] = Query(None, alias="from", description="Startzeit (ISO)"),
    to_date: Optional[datetime] = Query(None, alias="to", description="Endzeit (ISO)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> LearningListResponse:
    q = select(LearningArtifact)

    if artifact_type:
        q = q.where(LearningArtifact.artifact_type == artifact_type)
    if status:
        q = q.where(LearningArtifact.status == status)
    if agent_role:
        q = q.where(LearningArtifact.agent_role == agent_role)
    if source_type:
        q = q.where(LearningArtifact.source_type == source_type)
    if task_id:
        q = q.where(LearningArtifact.task_id == task_id)
    if epic_id:
        q = q.where(LearningArtifact.epic_id == epic_id)
    if project_id:
        q = q.where(LearningArtifact.project_id == project_id)
    if min_confidence is not None:
        q = q.where(LearningArtifact.confidence >= min_confidence)
    if from_date:
        q = q.where(LearningArtifact.created_at >= from_date)
    if to_date:
        q = q.where(LearningArtifact.created_at <= to_date)

    count_q = select(func.count()).select_from(q.subquery())
    total_count = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    q = q.order_by(LearningArtifact.created_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return LearningListResponse(
        data=[LearningArtifactResponse.model_validate(r) for r in rows],
        total_count=total_count,
        has_more=(offset + len(rows)) < total_count,
        page=page,
        page_size=page_size,
    )


# ── GET /api/learning/artifacts/{artifact_id} ────────────────────────────────

@router.get("/artifacts/{artifact_id}", response_model=LearningArtifactResponse)
async def get_learning_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> LearningArtifactResponse:
    row = await db.get(LearningArtifact, artifact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Learning artifact not found")
    return LearningArtifactResponse.model_validate(row)


# ── GET /api/learning/stats ───────────────────────────────────────────────────

@router.get("/stats", response_model=LearningStatsResponse)
async def get_learning_stats(
    project_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> LearningStatsResponse:
    q = select(
        LearningArtifact.artifact_type,
        LearningArtifact.status,
        func.count().label("count"),
    ).group_by(LearningArtifact.artifact_type, LearningArtifact.status)

    if project_id:
        q = q.where(LearningArtifact.project_id == project_id)

    rows = (await db.execute(q)).all()
    stats = [LearningStatsEntry(artifact_type=r.artifact_type, status=r.status, count=r.count) for r in rows]
    total = sum(s.count for s in stats)

    # Skill-candidates: execution_learning artifacts mit kind=skill_candidate im detail
    sc_q = select(func.count()).where(
        LearningArtifact.artifact_type == "execution_learning",
        LearningArtifact.status != "suppressed",
        LearningArtifact.detail["kind"].astext == "skill_candidate",
    )
    if project_id:
        sc_q = sc_q.where(LearningArtifact.project_id == project_id)
    skill_candidates = (await db.execute(sc_q)).scalar_one()

    return LearningStatsResponse(stats=stats, total=total, skill_candidates=skill_candidates)
