"""APScheduler-Jobs (TASK-2-007: Audit-Retention-Cron).

Wird im FastAPI-lifespan gestartet und läuft als Hintergrund-Scheduler.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _audit_retention_job() -> None:
    """Setzt input_payload + output_payload auf NULL für Einträge älter als AUDIT_RETENTION_DAYS."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    from app.db import AsyncSessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.audit_retention_days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("""
                UPDATE mcp_invocations
                SET input_payload = NULL,
                    output_payload = NULL
                WHERE created_at < :cutoff
                  AND (input_payload IS NOT NULL OR output_payload IS NOT NULL)
            """),
            {"cutoff": cutoff},
        )
        await db.commit()
        count = result.rowcount
        if count:
            logger.info("Audit-Retention: %d Einträge bereinigt (älter als %d Tage)", count, settings.audit_retention_days)


async def _prompt_history_retention_job() -> None:
    """Löscht prompt_history-Einträge älter als HIVEMIND_PROMPT_HISTORY_RETENTION_DAYS (Default: 180)."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    from app.db import AsyncSessionLocal

    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.hivemind_prompt_history_retention_days)

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

    scheduler.start()
    logger.info(
        "Scheduler gestartet — audit_retention 03:00 UTC, prompt_history_cleanup 03:05 UTC"
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
