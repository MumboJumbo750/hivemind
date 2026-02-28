"""Federation Service — TASK-F-006 & TASK-F-009.

Service-layer hooks for federation:
- publish_skill_to_federation: create outbox entries when a skill is federated
- publish_wiki_to_federation: create outbox entries when a wiki article is federated
- notify_peer_task_update: create outbox entry when a delegated task changes state
"""
import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.federation import Node, NodeIdentity
from app.models.skill import Skill
from app.models.sync import SyncOutbox
from app.models.wiki import WikiArticle

logger = logging.getLogger(__name__)


async def _get_own_node_id(db: AsyncSession) -> uuid.UUID | None:
    """Get the local node's ID from node_identity."""
    result = await db.execute(select(NodeIdentity))
    identity = result.scalar_one_or_none()
    return identity.node_id if identity else None


async def _get_active_peers(db: AsyncSession, own_node_id: uuid.UUID | None) -> list[Node]:
    """Get all active peer nodes (excluding self)."""
    q = select(Node).where(
        Node.status == "active",
        Node.deleted_at.is_(None),
    )
    if own_node_id:
        q = q.where(Node.id != own_node_id)
    result = await db.execute(q)
    return list(result.scalars().all())


async def publish_skill_to_federation(db: AsyncSession, skill_id: uuid.UUID) -> int:
    """Create outbox entries for all active peers when a skill is federated.

    Returns the number of outbox entries created.
    """
    if not settings.hivemind_federation_enabled:
        return 0

    # Load skill
    result = await db.execute(select(Skill).where(Skill.id == skill_id))
    skill = result.scalar_one_or_none()
    if skill is None:
        logger.warning("Skill %s not found for federation publish", skill_id)
        return 0

    # Only publish federated + active skills
    if skill.lifecycle != "active" or skill.federation_scope != "federated":
        return 0

    own_node_id = await _get_own_node_id(db)
    peers = await _get_active_peers(db, own_node_id)

    if not peers:
        return 0

    payload = {
        "title": skill.title,
        "content": skill.content,
        "service_scope": skill.service_scope or [],
        "stack": skill.stack or [],
        "skill_type": skill.skill_type,
        "lifecycle": skill.lifecycle,
        "version": skill.version,
    }

    count = 0
    for peer in peers:
        dedup_key = f"skill:{skill_id}:{peer.id}"

        # Check for existing entry with same dedup_key
        existing = await db.execute(
            select(SyncOutbox).where(SyncOutbox.dedup_key == dedup_key)
        )
        if existing.scalar_one_or_none():
            continue

        entry = SyncOutbox(
            dedup_key=dedup_key,
            direction="peer_outbound",
            system="federation",
            target_node_id=peer.id,
            entity_type="skill_published",
            entity_id=str(skill_id),
            payload=payload,
        )
        db.add(entry)
        count += 1

    if count:
        await db.flush()
        logger.info("Created %d outbox entries for federated skill '%s'", count, skill.title)

    return count


async def publish_wiki_to_federation(db: AsyncSession, article_id: uuid.UUID) -> int:
    """Create outbox entries for all active peers when a wiki article is federated.

    Returns the number of outbox entries created.
    """
    if not settings.hivemind_federation_enabled:
        return 0

    result = await db.execute(select(WikiArticle).where(WikiArticle.id == article_id))
    article = result.scalar_one_or_none()
    if article is None:
        logger.warning("Wiki article %s not found for federation publish", article_id)
        return 0

    if article.federation_scope != "federated":
        return 0

    own_node_id = await _get_own_node_id(db)
    peers = await _get_active_peers(db, own_node_id)

    if not peers:
        return 0

    payload = {
        "title": article.title,
        "slug": article.slug,
        "content": article.content,
        "tags": article.tags or [],
        "version": article.version,
    }

    count = 0
    for peer in peers:
        dedup_key = f"wiki:{article_id}:{peer.id}"

        existing = await db.execute(
            select(SyncOutbox).where(SyncOutbox.dedup_key == dedup_key)
        )
        if existing.scalar_one_or_none():
            continue

        entry = SyncOutbox(
            dedup_key=dedup_key,
            direction="peer_outbound",
            system="federation",
            target_node_id=peer.id,
            entity_type="wiki_published",
            entity_id=str(article_id),
            payload=payload,
        )
        db.add(entry)
        count += 1

    if count:
        await db.flush()
        logger.info("Created %d outbox entries for federated wiki '%s'", count, article.title)

    return count


async def notify_peer_task_update(
    db: AsyncSession,
    task_id: uuid.UUID,
    task_key: str,
    new_state: str,
    assigned_node_id: uuid.UUID,
    result_text: str | None = None,
) -> bool:
    """Create outbox entry when a delegated task changes state.

    Returns True if an outbox entry was created.
    """
    if not settings.hivemind_federation_enabled:
        return False

    dedup_key = f"task_update:{task_id}:{new_state}"

    # Check for existing
    existing = await db.execute(
        select(SyncOutbox).where(SyncOutbox.dedup_key == dedup_key)
    )
    if existing.scalar_one_or_none():
        return False

    payload = {
        "external_id": task_key,
        "state": new_state,
        "result": result_text,
    }

    entry = SyncOutbox(
        dedup_key=dedup_key,
        direction="peer_outbound",
        system="federation",
        target_node_id=assigned_node_id,
        entity_type="task_updated",
        entity_id=str(task_id),
        payload=payload,
    )
    db.add(entry)
    await db.flush()
    logger.info("Outbox entry for task update %s → %s (peer: %s)", task_key, new_state, assigned_node_id)
    return True
