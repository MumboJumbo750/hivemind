"""Outbox Consumer for peer_outbound — TASK-F-005.

APScheduler job that processes ``sync_outbox`` entries with
``direction='peer_outbound'``. Sends HTTP POST to peer nodes with
Ed25519-signed request bodies. Moves failed entries to DLQ after max attempts.
"""
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.federation import Node
from app.models.sync import SyncDeadLetter, SyncOutbox
from app.services.federation_auth import sign_request

logger = logging.getLogger(__name__)

# Mapping from outbox event_type to Federation API path
EVENT_TYPE_TO_PATH: dict[str, str] = {
    "skill_published": "skill/publish",
    "wiki_published": "wiki/publish",
    "epic_shared": "epic/share",
    "task_updated": "task/update",
    "sync": "sync",
}

BATCH_SIZE = 50
HTTP_TIMEOUT = 10.0


async def process_outbox() -> None:
    """Process pending peer_outbound entries from sync_outbox."""
    if not settings.hivemind_federation_enabled:
        return

    async with AsyncSessionLocal() as db:
        # Load batch of pending outbox entries
        result = await db.execute(
            select(SyncOutbox)
            .where(
                SyncOutbox.direction == "peer_outbound",
                SyncOutbox.state == "pending",
                SyncOutbox.attempts < settings.hivemind_dlq_max_attempts,
            )
            .order_by(SyncOutbox.created_at.asc())
            .limit(BATCH_SIZE)
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

                    # Move to DLQ if max attempts reached
                    if entry.attempts >= settings.hivemind_dlq_max_attempts:
                        await _move_to_dlq(db, entry, str(exc))

        await db.commit()


async def _process_entry(
    db: AsyncSession,
    client: httpx.AsyncClient,
    entry: SyncOutbox,
) -> None:
    """Send a single outbox entry to the target peer."""
    # Resolve target node
    if not entry.target_node_id:
        logger.warning("Outbox entry %s has no target_node_id — skipping", entry.id)
        entry.attempts += 1
        return

    result = await db.execute(
        select(Node).where(Node.id == entry.target_node_id)
    )
    target_node = result.scalar_one_or_none()

    if target_node is None:
        logger.warning("Target node %s not found for outbox entry %s", entry.target_node_id, entry.id)
        entry.attempts += 1
        return

    if target_node.status != "active":
        logger.debug("Target node %s is %s — skipping entry %s", target_node.node_name, target_node.status, entry.id)
        return  # Don't increment attempts for inactive peers — retry later

    # Determine endpoint path
    path = EVENT_TYPE_TO_PATH.get(entry.entity_type, entry.entity_type)
    url = f"{target_node.node_url.rstrip('/')}/federation/{path}"

    # Serialize payload
    body = json.dumps(entry.payload).encode("utf-8")

    # Sign the request
    node_id_str, signature = await sign_request(body)

    # Send
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
        # Success — delete entry
        await db.delete(entry)
        logger.debug("Outbox entry %s delivered to %s", entry.id, target_node.node_name)
    else:
        # Direct delivery failed — try relay if hub_relay mode
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
            # Failure — increment attempts
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
    logger.warning("Outbox entry %s moved to DLQ: %s", entry.id, error)
