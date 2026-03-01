"""Notification REST Endpoints — TASK-6-015.

GET  /api/notifications          — list notifications (paginated, filterable)
PATCH /api/notifications/{id}/read — mark as read
GET  /api/notifications/unread-count — unread count
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.services.notification_service import (
    get_notifications,
    get_unread_count,
    mark_notification_read,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    priority: str
    title: str
    body: str | None = None
    link: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UnreadCountResponse(BaseModel):
    count: int


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    read: Optional[bool] = Query(None, description="Filter by read status"),
    priority: Optional[str] = Query(None, description="Filter by priority (action_now/soon/fyi)"),
    type: Optional[str] = Query(None, description="Filter by notification type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    """List notifications for the current user."""
    notifications = await get_notifications(
        db,
        actor.id,
        read_filter=read,
        priority_filter=priority,
        type_filter=type,
        limit=limit,
        offset=offset,
    )
    return notifications


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    """Get count of unread notifications."""
    count = await get_unread_count(db, actor.id)
    return UnreadCountResponse(count=count)


@router.patch("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
):
    """Mark a notification as read."""
    success = await mark_notification_read(db, actor.id, str(notification_id))
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.commit()
    return {"status": "read", "notification_id": str(notification_id)}
