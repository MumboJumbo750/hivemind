"""Decision-Request SLA Enforcement Cron — TASK-6-004.

Checks open decision_requests against their sla_due_at:
  - 24h elapsed → notify owner
  - 48h elapsed → notify backup_owner (skip if NULL)
  - 72h elapsed → auto-escalate: task blocked→escalated,
    DR state→expired, notify all admins

All notifications are idempotent via notification_service dedup.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal
from app.models.decision import DecisionRequest
from app.models.epic import Epic
from app.models.task import Task
from app.services.audit import write_audit
from app.services.notification_service import (
    create_notification,
    get_admin_user_ids,
    notify_users,
)

logger = logging.getLogger(__name__)

SYSTEM_ACTOR = uuid.UUID("00000000-0000-0000-0000-000000000000")


async def decision_sla_cron_job() -> None:
    """Check open decision request SLAs and enforce escalation."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            now = datetime.now(timezone.utc)

            # Get all open decision requests with SLA
            result = await db.execute(
                select(DecisionRequest).where(
                    and_(
                        DecisionRequest.state == "open",
                        DecisionRequest.sla_due_at.isnot(None),
                    )
                )
            )
            drs = result.scalars().all()

            for dr in drs:
                sla = dr.sla_due_at
                elapsed = now - sla if now > sla else timedelta(0)
                age = now - dr.created_at
                entity_id = str(dr.id)

                # ── 72h → auto-escalate ───────────────────────────────
                if age >= timedelta(hours=72):
                    await _escalate_decision_request(db, dr, now)
                    continue

                # ── 48h → notify backup_owner ─────────────────────────
                if age >= timedelta(hours=48):
                    if dr.backup_owner_id:
                        await create_notification(
                            db,
                            user_id=dr.backup_owner_id,
                            notification_type="decision_escalated_backup",
                            body=f"Decision Request seit >48h offen. Bitte eingreifen.",
                            link=f"/tasks/{await _task_key_for_dr(db, dr)}",
                            entity_type="decision_request",
                            entity_id=entity_id,
                        )
                    # If no backup_owner, skip (admins get notified at 72h)
                    continue

                # ── 24h → notify owner ────────────────────────────────
                if age >= timedelta(hours=24):
                    if dr.owner_id:
                        await create_notification(
                            db,
                            user_id=dr.owner_id,
                            notification_type="decision_request",
                            body=f"Decision Request seit >24h offen. Bitte auflösen.",
                            link=f"/tasks/{await _task_key_for_dr(db, dr)}",
                            entity_type="decision_request",
                            entity_id=entity_id,
                        )

            if drs:
                logger.info("Decision-SLA-Cron: %d offene DRs geprüft", len(drs))


async def _task_key_for_dr(db: AsyncSession, dr: DecisionRequest) -> str:
    """Get the task_key for a decision request."""
    if dr.task_id:
        result = await db.execute(
            select(Task.task_key).where(Task.id == dr.task_id)
        )
        row = result.scalar_one_or_none()
        if row:
            return row
    return "unknown"


async def _escalate_decision_request(
    db: AsyncSession, dr: DecisionRequest, now: datetime
) -> None:
    """72h breach: expire DR, escalate task, notify admins."""
    # Set DR state to expired
    dr.state = "expired"
    dr.version += 1
    await db.flush()

    # Escalate associated task: blocked → escalated
    if dr.task_id:
        result = await db.execute(
            select(Task).where(Task.id == dr.task_id)
        )
        task = result.scalar_one_or_none()
        if task and task.state == "blocked":
            task.state = "escalated"
            task.version += 1
            await db.flush()

    # Notify all admins
    admin_ids = await get_admin_user_ids(db)
    if admin_ids:
        task_key = await _task_key_for_dr(db, dr)
        await notify_users(
            db,
            user_ids=admin_ids,
            notification_type="decision_escalated_admin",
            body=f"Decision Request 72h überschritten. Task {task_key} eskaliert. Manueller Admin-Eingriff erforderlich.",
            link=f"/tasks/{task_key}",
            entity_type="decision_request",
            entity_id=str(dr.id),
        )

    # Audit log
    await write_audit(
        tool_name="auto_decision_sla_escalation",
        actor_id=SYSTEM_ACTOR,
        actor_role="system",
        input_payload={"decision_request_id": str(dr.id), "task_id": str(dr.task_id)},
        target_id=str(dr.id),
    )

    logger.info("Decision Request %s expired + task escalated", dr.id)
