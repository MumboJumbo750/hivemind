"""Memory Ledger debug/admin REST API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.memory import MemoryEntry, MemorySession, MemorySummary
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/admin/memory", tags=["memory"])


class MemorySessionResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    agent_role: str
    scope: str
    scope_id: Optional[uuid.UUID] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    entry_count: int
    compacted: bool

    model_config = {"from_attributes": True}


class MemoryEntryResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    agent_role: str
    scope: str
    scope_id: Optional[uuid.UUID] = None
    session_id: uuid.UUID
    content: str
    tags: list[str]
    covered_by: Optional[uuid.UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MemorySummaryResponse(BaseModel):
    id: uuid.UUID
    actor_id: uuid.UUID
    agent_role: str
    scope: str
    scope_id: Optional[uuid.UUID] = None
    session_id: Optional[uuid.UUID] = None
    content: str
    source_entry_ids: list[uuid.UUID]
    source_fact_ids: list[uuid.UUID]
    source_count: int
    open_questions: list[str]
    graduated: bool
    graduated_to: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryListResponse(BaseModel):
    total_count: int
    has_more: bool
    page: int
    page_size: int


class MemorySessionListResponse(MemoryListResponse):
    data: list[MemorySessionResponse]


class MemoryEntryListResponse(MemoryListResponse):
    data: list[MemoryEntryResponse]


class MemorySummaryListResponse(MemoryListResponse):
    data: list[MemorySummaryResponse]


def _apply_scope_filter(q, model, scope: Optional[str], scope_id: Optional[uuid.UUID]):
    if scope:
        q = q.where(model.scope == scope)
    if scope_id:
        q = q.where(model.scope_id == scope_id)
    return q


@router.get("/sessions", response_model=MemorySessionListResponse)
async def list_memory_sessions(
    agent_role: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    scope_id: Optional[uuid.UUID] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> MemorySessionListResponse:
    q = select(MemorySession)
    if agent_role:
        q = q.where(MemorySession.agent_role == agent_role)
    q = _apply_scope_filter(q, MemorySession, scope, scope_id)

    total_count = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            q.order_by(MemorySession.started_at.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()
    return MemorySessionListResponse(
        data=[MemorySessionResponse.model_validate(row) for row in rows],
        total_count=total_count,
        has_more=(offset + len(rows)) < total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/entries", response_model=MemoryEntryListResponse)
async def list_memory_entries(
    agent_role: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    scope_id: Optional[uuid.UUID] = Query(None),
    uncovered_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> MemoryEntryListResponse:
    q = select(MemoryEntry)
    if agent_role:
        q = q.where(MemoryEntry.agent_role == agent_role)
    q = _apply_scope_filter(q, MemoryEntry, scope, scope_id)
    if uncovered_only:
        q = q.where(MemoryEntry.covered_by.is_(None))

    total_count = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            q.order_by(MemoryEntry.created_at.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()
    return MemoryEntryListResponse(
        data=[MemoryEntryResponse.model_validate(row) for row in rows],
        total_count=total_count,
        has_more=(offset + len(rows)) < total_count,
        page=page,
        page_size=page_size,
    )


@router.get("/summaries", response_model=MemorySummaryListResponse)
async def list_memory_summaries(
    agent_role: Optional[str] = Query(None),
    scope: Optional[str] = Query(None),
    scope_id: Optional[uuid.UUID] = Query(None),
    graduated: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> MemorySummaryListResponse:
    q = select(MemorySummary)
    if agent_role:
        q = q.where(MemorySummary.agent_role == agent_role)
    q = _apply_scope_filter(q, MemorySummary, scope, scope_id)
    if graduated is not None:
        q = q.where(MemorySummary.graduated.is_(graduated))

    total_count = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    offset = (page - 1) * page_size
    rows = (
        await db.execute(
            q.order_by(MemorySummary.created_at.desc()).offset(offset).limit(page_size)
        )
    ).scalars().all()
    return MemorySummaryListResponse(
        data=[MemorySummaryResponse.model_validate(row) for row in rows],
        total_count=total_count,
        has_more=(offset + len(rows)) < total_count,
        page=page,
        page_size=page_size,
    )