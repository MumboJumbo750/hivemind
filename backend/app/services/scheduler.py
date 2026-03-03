"""APScheduler-Jobs (TASK-2-007: Audit-Retention-Cron).

Wird im FastAPI-lifespan gestartet und läuft als Hintergrund-Scheduler.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _audit_retention_job() -> None:
    """Nullt alte Payloads und löscht sehr alte mcp_invocations-Rows vollständig."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from app.db import AsyncSessionLocal

    now = datetime.now(UTC)
    payload_cutoff = now - timedelta(days=settings.audit_retention_days)
    delete_cutoff = now - timedelta(days=settings.audit_row_deletion_days)

    async with AsyncSessionLocal() as db:
        nullify_result = await db.execute(
            text("""
                UPDATE mcp_invocations
                SET input_payload = NULL,
                    output_payload = NULL
                WHERE created_at < :payload_cutoff
                  AND (input_payload IS NOT NULL OR output_payload IS NOT NULL)
            """),
            {"payload_cutoff": payload_cutoff},
        )
        delete_result = await db.execute(
            text("""
                DELETE FROM mcp_invocations
                WHERE created_at < :delete_cutoff
            """),
            {"delete_cutoff": delete_cutoff},
        )
        await db.commit()
        nullified_count = nullify_result.rowcount
        deleted_count = delete_result.rowcount
        if nullified_count:
            logger.info(
                "Audit-Retention: %d Einträge bereinigt (älter als %d Tage)",
                nullified_count,
                settings.audit_retention_days,
            )
        if deleted_count:
            logger.info(
                "Audit-Retention: %d Einträge gelöscht (älter als %d Tage)",
                deleted_count,
                settings.audit_row_deletion_days,
            )


async def _prompt_history_retention_job() -> None:
    """Löscht prompt_history-Einträge älter als HIVEMIND_PROMPT_HISTORY_RETENTION_DAYS (Default: 180)."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from app.db import AsyncSessionLocal

    cutoff = datetime.now(UTC) - timedelta(days=settings.hivemind_prompt_history_retention_days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("DELETE FROM prompt_history WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        await db.commit()
        count = result.rowcount
        if count:
            logger.info(
                "PromptHistory-Retention: %d Einträge gelöscht (älter als %d Tage)",
                count,
                settings.hivemind_prompt_history_retention_days,
            )


async def _notification_retention_job() -> None:
    """Delete old notifications (TASK-6-009).

    - Read notifications older than NOTIFICATION_RETENTION_DAYS (default: 90)
    - Unread notifications older than NOTIFICATION_UNREAD_RETENTION_DAYS (default: 365)
    """
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from app.db import AsyncSessionLocal

    now = datetime.now(UTC)
    read_cutoff = now - timedelta(days=settings.notification_retention_days)
    unread_cutoff = now - timedelta(days=settings.notification_unread_retention_days)

    async with AsyncSessionLocal() as db:
        # Delete old read notifications
        result_read = await db.execute(
            text("""
                DELETE FROM notifications
                WHERE read = true AND created_at < :cutoff
            """),
            {"cutoff": read_cutoff},
        )

        # Delete very old unread notifications
        result_unread = await db.execute(
            text("""
                DELETE FROM notifications
                WHERE read = false AND created_at < :cutoff
            """),
            {"cutoff": unread_cutoff},
        )

        await db.commit()
        read_count = result_read.rowcount
        unread_count = result_unread.rowcount
        if read_count or unread_count:
            logger.info(
                "Notification-Retention: %d gelesene (>%dd) + %d ungelesene (>%dd) gelöscht",
                read_count,
                settings.notification_retention_days,
                unread_count,
                settings.notification_unread_retention_days,
            )


def start_scheduler() -> None:
    """Scheduler mit täglichem Audit-Retention-Job und PromptHistory-Retention-Job registrieren und starten."""
    scheduler.add_job(
        _audit_retention_job,
        trigger="cron",
        hour=3,
        minute=0,
        id="audit_retention",
        replace_existing=True,
    )

    scheduler.add_job(
        _prompt_history_retention_job,
        trigger="cron",
        hour=3,
        minute=5,
        id="prompt_history_cleanup",
        replace_existing=True,
    )

    # Notification Retention Cron — TASK-6-009
    scheduler.add_job(
        _notification_retention_job,
        trigger="cron",
        hour=3,
        minute=10,
        id="notification_retention",
        replace_existing=True,
    )

    # SLA Cron Job — checks epic deadlines and triggers notifications
    from app.services.sla_cron import sla_cron_job

    scheduler.add_job(
        sla_cron_job,
        trigger="interval",
        seconds=settings.hivemind_sla_cron_interval,
        id="sla_cron",
        replace_existing=True,
    )
    logger.info(
        "SLA cron registriert — alle %ds",
        settings.hivemind_sla_cron_interval,
    )

    # Decision-Request SLA Enforcement — checks open DRs for 24h/48h/72h
    from app.services.decision_sla_cron import decision_sla_cron_job

    scheduler.add_job(
        decision_sla_cron_job,
        trigger="interval",
        seconds=settings.hivemind_sla_cron_interval,
        id="decision_sla_cron",
        replace_existing=True,
    )
    logger.info("Decision-SLA cron registriert")

    # KPI cache refresh — stündlich (TASK-7-013)
    from app.services.kpi_service import refresh_kpi_cache

    scheduler.add_job(
        refresh_kpi_cache,
        trigger="interval",
        seconds=3600,
        id="kpi_cache",
        replace_existing=True,
    )
    logger.info("KPI cache job registriert — alle 3600s")

    # Inbound/Outbound consumers (YouTrack/Sentry) - independent from federation flag
    from app.services.outbox_consumer import process_inbound, process_outbound

    scheduler.add_job(
        process_inbound,
        trigger="interval",
        seconds=settings.hivemind_outbox_interval,
        id="inbound_consumer",
        replace_existing=True,
    )
    logger.info(
        "Inbound consumer registriert - alle %ds",
        settings.hivemind_outbox_interval,
    )

    scheduler.add_job(
        process_outbound,
        trigger="interval",
        seconds=settings.hivemind_outbox_interval,
        id="outbound_consumer",
        replace_existing=True,
    )
    logger.info(
        "Outbound consumer registriert - alle %ds",
        settings.hivemind_outbox_interval,
    )

    # Federation Outbox Consumer — process peer_outbound entries
    if settings.hivemind_federation_enabled:
        from app.services.outbox_consumer import process_outbox

        scheduler.add_job(
            process_outbox,
            trigger="interval",
            seconds=settings.hivemind_outbox_interval,
            id="outbox_consumer",
            replace_existing=True,
        )
        logger.info(
            "Outbox consumer registriert — alle %ds",
            settings.hivemind_outbox_interval,
        )

        # Heartbeat Service — ping peers and update status
        from app.services.heartbeat import heartbeat

        scheduler.add_job(
            heartbeat,
            trigger="interval",
            seconds=settings.hivemind_heartbeat_interval,
            id="heartbeat",
            replace_existing=True,
        )
        logger.info(
            "Heartbeat service registriert — alle %ds",
            settings.hivemind_heartbeat_interval,
        )

    # Phase 8 — Conductor + Auto-Review (only when HIVEMIND_CONDUCTOR_ENABLED=true)
    if settings.hivemind_conductor_enabled:
        from app.services.conductor import conductor_poll_job

        scheduler.add_job(
            conductor_poll_job,
            trigger="interval",
            seconds=30,
            id="conductor_poll",
            replace_existing=True,
        )
        logger.info("Conductor poll job registriert — alle 30s")

        from app.services.conductor_ide_timeout import ide_timeout_job

        scheduler.add_job(
            ide_timeout_job,
            trigger="interval",
            seconds=60,
            id="conductor_ide_timeout",
            replace_existing=True,
        )
        logger.info("Conductor IDE timeout job registriert — alle 60s")

        from app.services.auto_review_cron import auto_review_job

        scheduler.add_job(
            auto_review_job,
            trigger="interval",
            seconds=60,
            id="auto_review",
            replace_existing=True,
        )
        logger.info("Auto-Review job registriert — alle 60s")

    scheduler.start()
    logger.info(
        "Scheduler gestartet — audit_retention 03:00 UTC, prompt_history_cleanup 03:05 UTC"
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
