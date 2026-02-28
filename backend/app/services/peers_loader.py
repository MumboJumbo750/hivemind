"""peers.yaml-Loader — TASK-F-002.

Reads peer configuration from HIVEMIND_PEERS_CONFIG at app startup and
upserts peers into the ``nodes`` table. Only active when HIVEMIND_FEDERATION_ENABLED=true.
"""
import logging
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.federation import Node

logger = logging.getLogger(__name__)


async def load_peers(db: AsyncSession) -> None:
    """Read peers.yaml and upsert into nodes table. Idempotent via node_url."""
    if not settings.hivemind_federation_enabled:
        logger.debug("Federation disabled — peers.yaml loading skipped.")
        return

    config_path = Path(settings.hivemind_peers_config)
    if not config_path.exists():
        logger.warning("Peers config not found at %s — skipping peer loading.", config_path)
        return

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        logger.error("Invalid YAML in peers config %s: %s", config_path, exc)
        return
    except OSError as exc:
        logger.warning("Could not read peers config %s: %s", config_path, exc)
        return

    if not data or not isinstance(data.get("peers"), list):
        logger.warning("No 'peers' list found in %s — skipping.", config_path)
        return

    added = updated = skipped = 0
    for entry in data["peers"]:
        name = entry.get("name")
        url = entry.get("url")
        public_key = entry.get("public_key")

        if not all([name, url, public_key]):
            logger.warning(
                "Peer entry missing required fields (name, url, public_key): %s — skipped.",
                entry,
            )
            skipped += 1
            continue

        # Upsert via node_url
        result = await db.execute(select(Node).where(Node.node_url == url))
        existing = result.scalar_one_or_none()

        if existing:
            # Update name and public_key if changed
            changed = False
            if existing.node_name != name:
                existing.node_name = name
                changed = True
            if existing.public_key != public_key:
                existing.public_key = public_key
                changed = True
            if changed:
                updated += 1
            else:
                skipped += 1
        else:
            node = Node(
                node_name=name,
                node_url=url,
                public_key=public_key,
                status="active",
            )
            db.add(node)
            added += 1

    await db.flush()
    logger.info(
        "Peers loaded from %s: %d added, %d updated, %d skipped.",
        config_path,
        added,
        updated,
        skipped,
    )
