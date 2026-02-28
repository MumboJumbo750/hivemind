"""Hive Station Client — TASK-F-011.

Topology-aware client for Hive Station interactions:
- direct_mesh: no Hive Station contact (pure peers.yaml)
- hub_assisted: register + peer discovery + presence via Hive Station
- hub_relay: like hub_assisted + store-and-forward relay for failed direct sends
"""
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.federation import Node, NodeIdentity

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 10.0


class HiveStationClient:
    """Client for communicating with a Hive Station hub."""

    def __init__(self) -> None:
        self.base_url = settings.hivemind_hive_station_url.rstrip("/") if settings.hivemind_hive_station_url else ""
        self.token = settings.hivemind_hive_station_token
        self.topology = settings.hivemind_federation_topology

    @property
    def is_hub_mode(self) -> bool:
        return self.topology in ("hub_assisted", "hub_relay")

    @property
    def is_relay_enabled(self) -> bool:
        return self.topology == "hub_relay" and settings.hivemind_hive_relay_enabled

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def register(self, db: AsyncSession) -> bool:
        """Register this node with Hive Station. Returns True on success."""
        if not self.is_hub_mode or not self.base_url:
            return False

        result = await db.execute(select(NodeIdentity))
        identity = result.scalar_one_or_none()
        if identity is None:
            logger.warning("Cannot register: no node identity found")
            return False

        # Get own node info
        node_result = await db.execute(
            select(Node).where(Node.id == identity.node_id)
        )
        node = node_result.scalar_one_or_none()
        if node is None:
            return False

        payload = {
            "node_id": str(identity.node_id),
            "node_name": identity.node_name,
            "node_url": node.node_url,
            "public_key": identity.public_key,
        }

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/nodes/register",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                logger.info("Registered with Hive Station at %s", self.base_url)
                return True
        except (httpx.HTTPError, Exception) as exc:
            logger.warning("Failed to register with Hive Station: %s", exc)
            return False

    async def fetch_peers(self, db: AsyncSession) -> int:
        """Fetch peer list from Hive Station and merge into local nodes table.

        Returns the number of peers merged.
        """
        if not self.is_hub_mode or not self.base_url:
            return 0

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/api/nodes",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                peers_data = resp.json()
        except (httpx.HTTPError, Exception) as exc:
            logger.warning(
                "Failed to fetch peers from Hive Station (using local cache): %s", exc
            )
            return 0

        if not isinstance(peers_data, list):
            peers_data = peers_data.get("nodes", [])

        # Get own node ID to skip self
        id_result = await db.execute(select(NodeIdentity))
        identity = id_result.scalar_one_or_none()
        own_node_id = str(identity.node_id) if identity else None

        count = 0
        for p in peers_data:
            node_id_str = p.get("node_id", "")
            if node_id_str == own_node_id:
                continue

            node_url = p.get("node_url", "")
            if not node_url:
                continue

            # Upsert by node_url
            result = await db.execute(
                select(Node).where(Node.node_url == node_url)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.node_name = p.get("node_name", existing.node_name)
                existing.public_key = p.get("public_key", existing.public_key)
                existing.status = "active"
                existing.deleted_at = None
            else:
                new_node = Node(
                    node_name=p.get("node_name", "unknown"),
                    node_url=node_url,
                    public_key=p.get("public_key"),
                    status="active",
                )
                db.add(new_node)
            count += 1

        if count:
            await db.flush()
            logger.info("Merged %d peers from Hive Station", count)

        return count

    async def send_presence(self, db: AsyncSession) -> bool:
        """Send presence heartbeat to Hive Station. Returns True on success."""
        if not self.is_hub_mode or not self.base_url:
            return False

        result = await db.execute(select(NodeIdentity))
        identity = result.scalar_one_or_none()
        if identity is None:
            return False

        payload = {
            "node_id": str(identity.node_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/api/nodes/presence",
                    json=payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return True
        except (httpx.HTTPError, Exception) as exc:
            logger.warning("Failed to send presence to Hive Station: %s", exc)
            return False

    async def relay(self, target_node_url: str, path: str, payload: dict) -> bool:
        """Relay a message through Hive Station (hub_relay mode only).

        Used as fallback when direct transport to peer fails.
        Returns True if relay was accepted.
        """
        if not self.is_relay_enabled or not self.base_url:
            return False

        relay_payload = {
            "target_url": target_node_url,
            "path": path,
            "payload": payload,
        }

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/relay/forward",
                    json=relay_payload,
                    headers=self._headers(),
                )
                resp.raise_for_status()
                logger.info("Relayed message to %s via Hive Station", target_node_url)
                return True
        except (httpx.HTTPError, Exception) as exc:
            logger.error("Relay via Hive Station failed: %s", exc)
            return False


# Singleton-ish instance
hive_station = HiveStationClient()
