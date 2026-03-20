"""Agent Thread Sessions REST API — TASK-AUI-003.

GET /api/admin/agent-sessions — paginated list with filters
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
from app.models.agent_thread_session import AgentThreadSession
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/admin/agent-sessions", tags=["agent-sessions"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class AgentSessionResponse(BaseModel):
    id: uuid.UUID
    thread_key: str
    agent_role: str
    thread_policy: str
    project_id: Optional[uuid.UUID] = None
    epic_id: Optional[uuid.UUID] = None
    task_id: Optional[uuid.UUID] = None
    status: str
    dispatch_count: int
    summary: Optional[str] = None
    session_metadata: Optional[dict] = None
    started_at: datetime
    last_activity_at: datetime

    model_config = {"from_attributes": True}


class AgentSessionListResponse(BaseModel):
    data: list[AgentSessionResponse]
    total_count: int
    has_more: bool
    page: int
    page_size: int


# ── GET /api/admin/agent-sessions ────────────────────────────────────────────

@router.get("", response_model=AgentSessionListResponse)
async def list_agent_sessions(
    agent_role: Optional[str] = Query(None, description="Filter by agent role"),
    thread_policy: Optional[str] = Query(None, description="Filter by thread policy"),
    status: Optional[str] = Query(None, description="Filter by status (active/completed/expired)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _actor: CurrentActor = Depends(get_current_actor),
) -> AgentSessionListResponse:
    q = select(AgentThreadSession)

    if agent_role:
        q = q.where(AgentThreadSession.agent_role == agent_role)
    if thread_policy:
        q = q.where(AgentThreadSession.thread_policy == thread_policy)
    if status:
        q = q.where(AgentThreadSession.status == status)

    count_q = select(func.count()).select_from(q.subquery())
    total_count = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    q = q.order_by(AgentThreadSession.last_activity_at.desc()).offset(offset).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return AgentSessionListResponse(
        data=[AgentSessionResponse.model_validate(r) for r in rows],
        total_count=total_count,
        has_more=(offset + len(rows)) < total_count,
        page=page,
        page_size=page_size,
    )
