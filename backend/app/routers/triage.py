"""Triage REST endpoints - DLQ list + requeue/discard aliases (TASK-7-009).

GET  /api/triage/dead-letters                - paginated dead-letter list (cursor-based)
POST /api/triage/dead-letters/{id}/requeue   - alias for MCP requeue_dead_letter
POST /api/triage/dead-letters/{id}/discard   - alias for MCP discard_dead_letter
"""
from __future__ import annotations

import base64
import binascii
import json
import uuid
from datetime import UTC, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models.sync import SyncDeadLetter, SyncOutbox
from app.routers.deps import require_role
from app.schemas.auth import CurrentActor
from app.services.dlq_service import DlqError, discard_dead_letter, requeue_dead_letter

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

    stmt = (
        select(SyncDeadLetter)
        .options(selectinload(SyncDeadLetter.outbox_entry))
        .where(
            SyncDeadLetter.discarded_at.is_(None),
            SyncDeadLetter.requeued_at.is_(None),
        )
    )
    count_stmt = (
        select(func.count())
        .select_from(SyncDeadLetter)
        .where(
            SyncDeadLetter.discarded_at.is_(None),
            SyncDeadLetter.requeued_at.is_(None),
        )
    )

    if direction:
        stmt = stmt.join(SyncDeadLetter.outbox_entry)
        count_stmt = count_stmt.join(SyncDeadLetter.outbox_entry)
        stmt = stmt.where(SyncOutbox.direction == direction)
        count_stmt = count_stmt.where(SyncOutbox.direction == direction)

    if system:
        stmt = stmt.where(SyncDeadLetter.system == system)
        count_stmt = count_stmt.where(SyncDeadLetter.system == system)

    if cursor:
        cursor_failed_at, cursor_id = _decode_cursor(cursor)
        stmt = _apply_cursor(stmt, cursor_failed_at, cursor_id)

    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar_one() or 0)

    rows_result = await db.execute(
        stmt.order_by(
            SyncDeadLetter.failed_at.desc().nullslast(),
            SyncDeadLetter.id.desc(),
        ).limit(limit + 1)
    )
    rows = rows_result.scalars().all()
    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items = [
        DeadLetterItem(
            id=str(row.id),
            system=row.system,
            entity_type=row.entity_type,
            attempts=int(getattr(getattr(row, "outbox_entry", None), "attempts", 0) or 0),
            last_error=row.error,
            error=row.error,
            failed_at=row.failed_at,
            requeued_at=row.requeued_at,
            payload_preview=_payload_preview(row.payload),
        )
        for row in page_rows
    ]

    next_cursor = (
        _encode_cursor(page_rows[-1].failed_at, page_rows[-1].id)
        if has_more and page_rows
        else None
    )

    return DeadLetterListResponse(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total=total,
        limit=limit,
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


def _payload_preview(payload: dict | None, max_length: int = 200) -> Optional[str]:
    if not payload:
        return None
    try:
        text = json.dumps(payload)
    except (TypeError, ValueError):
        text = str(payload)
    return text[:max_length] if len(text) <= max_length else f"{text[:max_length]}..."


def _encode_cursor(failed_at: Optional[datetime], dead_letter_id: uuid.UUID) -> str:
    payload = {
        "failed_at": failed_at.astimezone(UTC).isoformat() if failed_at else None,
        "id": str(dead_letter_id),
    }
    token = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(token).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[Optional[datetime], uuid.UUID]:
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(f"{cursor}{padding}".encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        dead_letter_id = uuid.UUID(str(payload["id"]))

        failed_at_raw = payload.get("failed_at")
        if failed_at_raw is None:
            return None, dead_letter_id

        failed_at = datetime.fromisoformat(str(failed_at_raw).replace("Z", "+00:00"))
        if failed_at.tzinfo is None:
            failed_at = failed_at.replace(tzinfo=UTC)

        return failed_at, dead_letter_id
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        raise HTTPException(status_code=422, detail="Invalid cursor") from exc


def _apply_cursor(
    stmt,
    cursor_failed_at: Optional[datetime],
    cursor_id: uuid.UUID,
):
    if cursor_failed_at is None:
        return stmt.where(
            and_(
                SyncDeadLetter.failed_at.is_(None),
                SyncDeadLetter.id < cursor_id,
            )
        )

    return stmt.where(
        or_(
            SyncDeadLetter.failed_at.is_(None),
            SyncDeadLetter.failed_at < cursor_failed_at,
            and_(
                SyncDeadLetter.failed_at == cursor_failed_at,
                SyncDeadLetter.id < cursor_id,
            ),
        )
    )
