"""Heartbeat Service — TASK-F-010.

APScheduler job that pings all active peers via GET /federation/ping
and updates their status in the nodes table.
"""
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.federation import Node
from app.models.task import Task

logger = logging.getLogger(__name__)

PING_TIMEOUT = 5.0


async def heartbeat() -> None:
    """Ping all peers and update their status."""
    if not settings.hivemind_federation_enabled:
        return

    async with AsyncSessionLocal() as db:
        # Load all non-deleted peers
        result = await db.execute(
            select(Node).where(Node.deleted_at.is_(None))
        )
        peers = list(result.scalars().all())

        if not peers:
            return

        now = datetime.now(timezone.utc)
        timeout_threshold = now.timestamp() - settings.hivemind_peer_timeout

        async with httpx.AsyncClient(timeout=PING_TIMEOUT) as client:
            for peer in peers:
                try:
                    resp = await client.get(f"{peer.node_url}/federation/ping")
                    resp.raise_for_status()

                    # Successful ping
                    was_inactive = peer.status == "inactive"
                    peer.last_seen = now
                    peer.status = "active"

                    if was_inactive:
                        logger.info("Peer '%s' back online → active", peer.node_name)
                        # peer_online event (will be consumed by SSE in TASK-F-015)
                        await _emit_peer_event(db, peer, "peer_online")

                except (httpx.HTTPError, Exception) as exc:
                    logger.debug("Ping failed for '%s': %s", peer.node_name, exc)

                    # Check if peer should be marked inactive
                    if peer.last_seen:
                        last_seen_ts = peer.last_seen.timestamp()
                        if last_seen_ts < timeout_threshold and peer.status == "active":
                            peer.status = "inactive"
                            logger.warning(
                                "Peer '%s' marked inactive (last_seen: %s)",
                                peer.node_name,
                                peer.last_seen.isoformat(),
                            )
                            # Check for delegated tasks
                            has_delegated = await _has_delegated_tasks(db, peer.id)
                            if has_delegated:
                                await _emit_peer_event(db, peer, "peer_offline")

        # Hub-assisted / hub-relay: fetch peers from Hive Station + presence
        if settings.hivemind_federation_topology in ("hub_assisted", "hub_relay"):
            from app.services.hive_station import hive_station
            await hive_station.fetch_peers(db)
            await hive_station.send_presence(db)

        await db.commit()


async def _has_delegated_tasks(db: AsyncSession, node_id) -> bool:
    """Check if a peer has any non-done delegated tasks."""
    result = await db.execute(
        select(Task.id)
        .where(
            Task.assigned_node_id == node_id,
            Task.state.notin_(["done", "cancelled"]),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _emit_peer_event(db: AsyncSession, peer: Node, event_type: str) -> None:
    """Create a notification entry for peer status change and publish to SSE bus."""
    from app.models.sync import SyncOutbox
    from app.services.event_bus import publish

    # Publish to SSE event bus (TASK-F-015)
    publish("node_status", {
        "node_id": str(peer.id),
        "node_name": peer.node_name,
        "status": peer.status,
        "last_seen": peer.last_seen.isoformat() if peer.last_seen else None,
    })

    entry = SyncOutbox(
        dedup_key=f"{event_type}:{peer.id}:{datetime.now(timezone.utc).isoformat()}",
        direction="internal",
        system="federation",
        entity_type=event_type,
        entity_id=str(peer.id),
        payload={
            "node_id": str(peer.id),
            "node_name": peer.node_name,
            "event": event_type,
        },
    )
    db.add(entry)
    logger.info("Emitted %s event for peer '%s'", event_type, peer.node_name)
