"""Notification Service v2 — TASK-6-001.

DB-backed notifications with all 13 Phase 6 notification types.
Writes to the `notifications` table with priority classification
and idempotent dedup within 1h window.
Fires SSE events on creation.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.services.event_bus import publish

logger = logging.getLogger(__name__)

# ── Notification type definitions with default priority ────────────────────
# priority: action_now (critical), soon (zeitnah), fyi (informativ)
NOTIFICATION_TYPES: dict[str, dict] = {
    "sla_warning":                {"title": "SLA-Warnung: 4h bis Deadline",           "priority": "soon"},
    "sla_breach":                 {"title": "SLA überschritten",                      "priority": "action_now"},
    "sla_admin_fallback":         {"title": "SLA 24h überschritten — Admin-Fallback", "priority": "action_now"},
    "decision_request":           {"title": "Decision Request erstellt",              "priority": "soon"},
    "decision_escalated_backup":  {"title": "Decision Request: 48h ohne Auflösung",  "priority": "action_now"},
    "decision_escalated_admin":   {"title": "Decision Request: 72h eskaliert",        "priority": "action_now"},
    "escalation":                 {"title": "Task eskaliert",                         "priority": "action_now"},
    "skill_proposal":             {"title": "Neuer Skill-Vorschlag",                  "priority": "fyi"},
    "skill_merged":               {"title": "Skill gemerged",                         "priority": "fyi"},
    "task_done":                  {"title": "Task abgeschlossen",                     "priority": "fyi"},
    "dead_letter":                {"title": "Sync-Eintrag in DLQ verschoben",         "priority": "action_now"},
    "guard_failed":               {"title": "Guard fehlgeschlagen",                   "priority": "soon"},
    "task_assigned":              {"title": "Task zugewiesen",                        "priority": "soon"},
    "review_requested":           {"title": "Review angefordert",                     "priority": "soon"},
    "governance_promoted":        {"title": "Governance automatisch angehoben",       "priority": "soon"},
    "governance_demoted":         {"title": "Governance automatisch gesenkt",         "priority": "action_now"},
}

# Dedup window: same (user, type, entity_id) within this timeframe is skipped
DEDUP_WINDOW = timedelta(hours=1)


async def create_notification(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    notification_type: str,
    title: str | None = None,
    body: str = "",
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    priority: str | None = None,
) -> Notification | None:
    """Create a notification in the DB and fire SSE event.

    Returns the Notification object, or None if deduped/skipped.
    """
    try:
        type_info = NOTIFICATION_TYPES.get(notification_type, {})
        effective_title = title or type_info.get("title", notification_type)
        effective_priority = priority or type_info.get("priority", "fyi")

        # ── Idempotent dedup ──────────────────────────────────────────
        if entity_id:
            cutoff = datetime.now(timezone.utc) - DEDUP_WINDOW
            existing = await db.execute(
                select(Notification.id).where(
                    and_(
                        Notification.user_id == user_id,
                        Notification.type == notification_type,
                        Notification.entity_id == entity_id,
                        Notification.created_at >= cutoff,
                    )
                ).limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                logger.debug(
                    "Dedup: skipping %s for user %s entity %s",
                    notification_type, user_id, entity_id,
                )
                return None

        # ── Create notification ───────────────────────────────────────
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            priority=effective_priority,
            title=effective_title,
            body=body,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        db.add(notification)
        await db.flush()
        await db.refresh(notification)

        # ── Fire SSE event ────────────────────────────────────────────
        await publish(
            "notification_created",
            {
                "user_id": str(user_id),
                "notification_id": str(notification.id),
                "type": notification_type,
                "priority": effective_priority,
                "title": effective_title,
            },
            channel="notifications",
        )

        return notification

    except Exception:
        logger.exception("create_notification failed for type=%s user=%s", notification_type, user_id)
        return None


async def notify_users(
    db: AsyncSession,
    *,
    user_ids: list[uuid.UUID],
    notification_type: str,
    body: str = "",
    link: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    title: str | None = None,
    priority: str | None = None,
) -> list[Notification]:
    """Send the same notification to multiple users."""
    results = []
    for uid in user_ids:
        n = await create_notification(
            db,
            user_id=uid,
            notification_type=notification_type,
            title=title,
            body=body,
            link=link,
            entity_type=entity_type,
            entity_id=entity_id,
            priority=priority,
        )
        if n:
            results.append(n)
    return results


async def get_admin_user_ids(db: AsyncSession) -> list[uuid.UUID]:
    """Get all admin user IDs."""
    from app.models.user import User
    result = await db.execute(
        select(User.id).where(User.role == "admin")
    )
    return [row[0] for row in result.all()]


async def get_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    read_filter: bool | None = None,
    priority_filter: str | None = None,
    type_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    """Get notifications for a user with optional filters."""
    q = select(Notification).where(Notification.user_id == user_id)
    if read_filter is not None:
        q = q.where(Notification.read == read_filter)
    if priority_filter:
        q = q.where(Notification.priority == priority_filter)
    if type_filter:
        q = q.where(Notification.type == type_filter)
    q = q.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return list(result.scalars().all())


async def get_unread_count(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """Get count of unread notifications."""
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            and_(Notification.user_id == user_id, Notification.read == False)  # noqa: E712
        )
    )
    return result.scalar_one()


async def get_unread_notifications(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[Notification]:
    """Get unread notifications for a user."""
    return await get_notifications(db, user_id, read_filter=False)


async def mark_notification_read(
    db: AsyncSession,
    user_id: uuid.UUID,
    notification_id: str,
) -> bool:
    """Mark a notification as read."""
    nid = uuid.UUID(notification_id)
    result = await db.execute(
        update(Notification)
        .where(and_(Notification.id == nid, Notification.user_id == user_id))
        .values(read=True)
    )
    await db.flush()
    return result.rowcount > 0
