"""Outbox consumers for federation and external sync jobs.

- ``process_outbox`` handles ``direction='peer_outbound'`` (federation).
- ``process_outbound`` handles ``direction='outbound'`` (YouTrack/Sentry).
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.federation import Node
from app.models.sync import SyncDeadLetter, SyncOutbox
from app.services import event_bus
from app.services.federation_auth import sign_request
from app.services.intake_service import IntakeService
from app.services.sync_errors import PermanentSyncError

logger = logging.getLogger(__name__)

# Mapping from outbox entity_type to Federation API path
EVENT_TYPE_TO_PATH: dict[str, str] = {
    "skill_published": "skill/publish",
    "wiki_published": "wiki/publish",
    "epic_shared": "epic/share",
    "task_updated": "task/update",
    "sync": "sync",
}

PEER_BATCH_SIZE = 50
OUTBOUND_BATCH_SIZE = 10
INBOUND_BATCH_SIZE = 20
MAX_BACKOFF_SECONDS = 4 * 60 * 60
HTTP_TIMEOUT = 10.0


async def process_outbox() -> None:
    """Process pending peer_outbound entries from sync_outbox."""
    if not settings.hivemind_federation_enabled:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SyncOutbox)
            .where(
                SyncOutbox.direction == "peer_outbound",
                SyncOutbox.state == "pending",
                SyncOutbox.attempts < settings.hivemind_dlq_max_attempts,
            )
            .order_by(SyncOutbox.created_at.asc())
            .limit(PEER_BATCH_SIZE)
        )
        entries = list(result.scalars().all())

        if not entries:
            return

        logger.debug("Outbox consumer: processing %d entries", len(entries))

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            for entry in entries:
                try:
                    await _process_entry(db, client, entry)
                except Exception as exc:
                    logger.error("Outbox entry %s failed: %s", entry.id, exc)
                    entry.attempts += 1

                    if entry.attempts >= settings.hivemind_dlq_max_attempts:
                        await _move_to_dlq(db, entry, str(exc))

        await db.commit()


async def process_outbound() -> None:
    """Process pending outbound entries from sync_outbox."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SyncOutbox)
            .where(
                SyncOutbox.direction == "outbound",
                SyncOutbox.state == "pending",
                or_(
                    SyncOutbox.next_retry_at.is_(None),
                    SyncOutbox.next_retry_at <= func.now(),
                ),
            )
            .order_by(SyncOutbox.created_at.asc())
            .limit(OUTBOUND_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        entries = list(result.scalars().all())
        if not entries:
            return

        logger.debug("Outbound consumer: processing %d entries", len(entries))

        for entry in entries:
            try:
                await _dispatch_outbound(entry)
                await db.delete(entry)
            except PermanentSyncError as exc:
                logger.error("Outbound entry %s permanent failure: %s", entry.id, exc)
                entry.attempts = settings.hivemind_dlq_max_attempts
                await _move_to_dlq(db, entry, str(exc))
            except Exception as exc:
                logger.error("Outbound entry %s failed: %s", entry.id, exc)
                entry.attempts += 1

                if entry.attempts >= settings.hivemind_dlq_max_attempts:
                    await _move_to_dlq(db, entry, str(exc))
                    continue

                backoff_seconds = min(2 ** entry.attempts * 60, MAX_BACKOFF_SECONDS)
                entry.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)

        await db.commit()


async def process_inbound() -> None:
    """Process unrouted inbound entries from sync_outbox."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SyncOutbox)
            .where(
                SyncOutbox.direction == "inbound",
                SyncOutbox.routing_state == "unrouted",
                SyncOutbox.state == "pending",
                or_(
                    SyncOutbox.routing_detail.is_(None),
                    SyncOutbox.routing_detail["intake_stage"].astext.is_(None),
                    SyncOutbox.routing_detail["intake_stage"].astext != "triage_pending",
                ),
                or_(
                    SyncOutbox.next_retry_at.is_(None),
                    SyncOutbox.next_retry_at <= func.now(),
                ),
            )
            .order_by(SyncOutbox.created_at.asc())
            .limit(INBOUND_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        entries = list(result.scalars().all())
        if not entries:
            return

        logger.debug("Inbound consumer: processing %d entries", len(entries))

        for entry in entries:
            try:
                outcome = await _dispatch_inbound(entry, db)
                IntakeService(db).apply_inbound_outcome(entry, outcome)
            except Exception as exc:
                logger.error("Inbound entry %s failed: %s", entry.id, exc)
                entry.attempts += 1

                if entry.attempts >= settings.hivemind_dlq_max_attempts:
                    await _move_to_dlq(db, entry, str(exc))
                    continue

                backoff_seconds = min(2 ** entry.attempts * 60, MAX_BACKOFF_SECONDS)
                entry.next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)

        await db.commit()


async def _dispatch_outbound(entry: SyncOutbox) -> None:
    """Dispatch one outbound entry to the matching integration service."""
    if entry.system == "youtrack":
        from app.services.youtrack_sync import YouTrackSyncService

        service = YouTrackSyncService()
        await service.process_outbound(entry)
        return

    if entry.system == "sentry":
        from app.services.sentry_aggregation import SentryAggregationService

        service = SentryAggregationService()
        await service.process_outbound(entry)
        return

    raise ValueError(f"Unsupported outbound system: {entry.system}")


async def _dispatch_inbound(entry: SyncOutbox, db: AsyncSession) -> dict:
    """Dispatch one inbound entry to the matching integration service."""
    intake_service = IntakeService(db)
    if entry.system == "sentry":
        from app.services.sentry_aggregation import SentryAggregationService

        service = SentryAggregationService()
        payload = entry.raw_payload if isinstance(entry.raw_payload, dict) else entry.payload
        await service.process_sentry_event(payload)
        return intake_service.resolve_inbound_outcome(entry)

    if entry.system == "youtrack":
        from app.services.youtrack_sync import YouTrackSyncService

        service = YouTrackSyncService()
        await service.process_inbound(entry.payload)
        return intake_service.resolve_inbound_outcome(entry)

    raise ValueError(f"Unsupported inbound system: {entry.system}")


async def _process_entry(
    db: AsyncSession,
    client: httpx.AsyncClient,
    entry: SyncOutbox,
) -> None:
    """Send a single peer_outbound entry to the target peer node."""
    if not entry.target_node_id:
        logger.warning("Outbox entry %s has no target_node_id, skipping", entry.id)
        entry.attempts += 1
        return

    result = await db.execute(select(Node).where(Node.id == entry.target_node_id))
    target_node = result.scalar_one_or_none()

    if target_node is None:
        logger.warning("Target node %s not found for outbox entry %s", entry.target_node_id, entry.id)
        entry.attempts += 1
        return

    if target_node.status != "active":
        logger.debug(
            "Target node %s is %s, skipping entry %s",
            target_node.node_name,
            target_node.status,
            entry.id,
        )
        return

    path = EVENT_TYPE_TO_PATH.get(entry.entity_type, entry.entity_type)
    url = f"{target_node.node_url.rstrip('/')}/federation/{path}"

    body = json.dumps(entry.payload).encode("utf-8")
    node_id_str, signature = await sign_request(body)

    response = await client.post(
        url,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Node-ID": node_id_str,
            "X-Node-Signature": signature,
        },
    )

    if 200 <= response.status_code < 300:
        await db.delete(entry)
        logger.debug("Outbox entry %s delivered to %s", entry.id, target_node.node_name)
        return

    relayed = False
    if settings.hivemind_federation_topology == "hub_relay" and settings.hivemind_hive_relay_enabled:
        from app.services.hive_station import hive_station

        relayed = await hive_station.relay(
            target_node_url=target_node.node_url,
            path=f"federation/{path}",
            payload=entry.payload,
        )
        if relayed:
            await db.delete(entry)
            logger.info("Outbox entry %s relayed via Hive Station", entry.id)

    if not relayed:
        entry.attempts += 1
        logger.warning(
            "Outbox delivery to %s failed (HTTP %d): %s",
            url,
            response.status_code,
            response.text[:200],
        )

        if entry.attempts >= settings.hivemind_dlq_max_attempts:
            await _move_to_dlq(db, entry, f"HTTP {response.status_code}: {response.text[:200]}")


async def _move_to_dlq(db: AsyncSession, entry: SyncOutbox, error: str) -> None:
    """Move a failed outbox entry to the dead letter queue."""
    dead_letter = SyncDeadLetter(
        outbox_id=entry.id,
        system=entry.system,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        payload=entry.payload,
        error=error,
    )
    db.add(dead_letter)
    entry.state = "dead_letter"
    await db.flush()
    event_bus.publish(
        "triage_dlq_updated",
        {
            "action": "created",
            "dead_letter_id": str(dead_letter.id),
            "system": entry.system,
            "entity_type": entry.entity_type,
        },
        channel="triage",
    )
    logger.warning("Outbox entry %s moved to DLQ: %s", entry.id, error)
