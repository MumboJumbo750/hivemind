"""SLA Cron Service — TASK-6-002.

Checks epic SLA deadlines and sends notifications:
  - 4h before SLA → sla_warning to epic owner
  - SLA breached → sla_breach to backup_owner (or admins if NULL)
  - 24h after SLA → sla_admin_fallback to all admins
All notifications are idempotent (dedup in notification_service).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.epic import Epic
from app.services.notification_service import (
    create_notification,
    get_admin_user_ids,
    notify_users,
)

logger = logging.getLogger(__name__)


async def sla_cron_job() -> None:
    """Check epic SLA deadlines and trigger notifications."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            now = datetime.now(timezone.utc)
            warning_threshold = now + timedelta(hours=4)

            # Get all epics with SLA deadlines that are relevant
            result = await db.execute(
                select(Epic).where(
                    and_(
                        Epic.sla_due_at.isnot(None),
                        Epic.state.notin_(["done", "cancelled"]),
                    )
                )
            )
            epics = result.scalars().all()

            for epic in epics:
                sla = epic.sla_due_at
                if sla is None:
                    continue

                entity_id = str(epic.id)

                # ── 24h after SLA → admin fallback ────────────────────
                if sla + timedelta(hours=24) <= now:
                    admin_ids = await get_admin_user_ids(db)
                    if admin_ids:
                        await notify_users(
                            db,
                            user_ids=admin_ids,
                            notification_type="sla_admin_fallback",
                            body=f"Epic '{epic.title}' ({epic.epic_key}) SLA ist seit >24h überschritten. Admin-Eingriff erforderlich.",
                            link=f"/epics/{epic.epic_key}",
                            entity_type="epic",
                            entity_id=entity_id,
                        )

                # ── SLA breached → backup_owner or admins ─────────────
                elif sla <= now:
                    if epic.backup_owner_id:
                        await create_notification(
                            db,
                            user_id=epic.backup_owner_id,
                            notification_type="sla_breach",
                            body=f"Epic '{epic.title}' ({epic.epic_key}) SLA ist überschritten.",
                            link=f"/epics/{epic.epic_key}",
                            entity_type="epic",
                            entity_id=entity_id,
                        )
                    else:
                        # No backup owner → notify admins directly
                        admin_ids = await get_admin_user_ids(db)
                        if admin_ids:
                            await notify_users(
                                db,
                                user_ids=admin_ids,
                                notification_type="sla_breach",
                                body=f"Epic '{epic.title}' ({epic.epic_key}) SLA überschritten. Kein Backup-Owner gesetzt.",
                                link=f"/epics/{epic.epic_key}",
                                entity_type="epic",
                                entity_id=entity_id,
                            )

                # ── 4h before SLA → warning to owner ──────────────────
                elif sla <= warning_threshold:
                    if epic.owner_id:
                        await create_notification(
                            db,
                            user_id=epic.owner_id,
                            notification_type="sla_warning",
                            body=f"Epic '{epic.title}' ({epic.epic_key}) SLA-Deadline in weniger als 4 Stunden.",
                            link=f"/epics/{epic.epic_key}",
                            entity_type="epic",
                            entity_id=entity_id,
                        )

            count = len(epics)
            if count:
                logger.info("SLA-Cron: %d Epics geprüft", count)
