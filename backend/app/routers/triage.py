"""Triage REST endpoints - DLQ list + requeue/discard aliases (TASK-7-009).

GET  /api/triage/dead-letters                - paginated dead-letter list (cursor-based)
POST /api/triage/dead-letters/{id}/requeue   - alias for MCP requeue_dead_letter
POST /api/triage/dead-letters/{id}/discard   - alias for MCP discard_dead_letter
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import require_role
from app.schemas.auth import CurrentActor
from app.services.dlq_service import DlqError, discard_dead_letter, requeue_dead_letter
from app.services.triage_service import list_dead_letters_page

router = APIRouter(prefix="/triage", tags=["triage"])


class DeadLetterItem(BaseModel):
    id: str
    system: str
    entity_type: str
    attempts: int = 0
    last_error: Optional[str] = None
    error: Optional[str] = None
    failed_at: Optional[datetime] = None
    requeued_at: Optional[datetime] = None
    payload_preview: Optional[str] = None


class DeadLetterListResponse(BaseModel):
    items: list[DeadLetterItem]
    next_cursor: Optional[str] = None
    has_more: bool
    total: int
    limit: int


class RequeueDeadLetterData(BaseModel):
    id: str
    status: Literal["requeued"]
    new_outbox_id: str
    requeued_by: str
    requeued_at: datetime


class RequeueDeadLetterResponse(BaseModel):
    data: RequeueDeadLetterData


class DiscardDeadLetterData(BaseModel):
    id: str
    status: Literal["discarded"]
    discarded_by: str
    discarded_at: datetime


class DiscardDeadLetterResponse(BaseModel):
    data: DiscardDeadLetterData


@router.get("/dead-letters", response_model=DeadLetterListResponse)
async def list_dead_letters(
    system: Optional[str] = Query(None, description="Filter by system (youtrack/sentry)"),
    direction: Optional[str] = Query(None, description="Filter by outbox direction"),
    cursor: Optional[str] = Query(None, description="Opaque cursor for next page"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "triage")),
) -> DeadLetterListResponse:
    del actor

    page = await list_dead_letters_page(
        db,
        system=system,
        direction=direction,
        cursor=cursor,
        limit=limit,
    )

    return DeadLetterListResponse(
        items=[DeadLetterItem(**item) for item in page["items"]],
        next_cursor=page["next_cursor"],
        has_more=page["has_more"],
        total=page["total"],
        limit=page["limit"],
    )


@router.post(
    "/dead-letters/{dead_letter_id}/requeue",
    response_model=RequeueDeadLetterResponse,
)
async def requeue_dead_letter_endpoint(
    dead_letter_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "triage")),
) -> RequeueDeadLetterResponse:
    try:
        async with db.begin():
            result = await requeue_dead_letter(db, dead_letter_id, actor.id)
        return RequeueDeadLetterResponse(data=RequeueDeadLetterData.model_validate(result))
    except DlqError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post(
    "/dead-letters/{dead_letter_id}/discard",
    response_model=DiscardDeadLetterResponse,
)
async def discard_dead_letter_endpoint(
    dead_letter_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "triage")),
) -> DiscardDeadLetterResponse:
    try:
        async with db.begin():
            result = await discard_dead_letter(db, dead_letter_id, actor.id)
        return DiscardDeadLetterResponse(data=DiscardDeadLetterData.model_validate(result))
    except DlqError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
