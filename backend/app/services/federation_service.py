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


# ─── Node / Identity helpers ──────────────────────────────────────────────────


async def get_own_identity(db: AsyncSession):
    """Return the local NodeIdentity row, or None."""
    result = await db.execute(select(NodeIdentity))
    return result.scalar_one_or_none()


async def get_node_by_id(db: AsyncSession, node_id: uuid.UUID):
    """Return a Node by primary key, or None."""
    result = await db.execute(select(Node).where(Node.id == node_id))
    return result.scalar_one_or_none()


async def get_peer_node_by_url(db: AsyncSession, node_url: str):
    """Return a Node matching the given URL, or None."""
    result = await db.execute(select(Node).where(Node.node_url == node_url))
    return result.scalar_one_or_none()


async def list_peer_nodes(db: AsyncSession) -> list:
    """List all non-deleted Nodes in name order."""
    result = await db.execute(
        select(Node).where(Node.deleted_at.is_(None)).order_by(Node.node_name)
    )
    return list(result.scalars().all())


async def create_peer_node(
    db: AsyncSession,
    node_name: str,
    node_url: str,
    public_key: str | None = None,
):
    """Create, flush, commit and return a new Node."""
    node = Node(
        node_name=node_name,
        node_url=node_url,
        public_key=public_key,
        status="active",
    )
    db.add(node)
    await db.flush()
    await db.refresh(node)
    await db.commit()
    return node


async def update_peer_node(
    db: AsyncSession,
    node_id: uuid.UUID,
    status: str | None = None,
    node_name: str | None = None,
):
    """Update a peer node's mutable fields. Returns node or None if not found."""
    result = await db.execute(
        select(Node).where(Node.id == node_id, Node.deleted_at.is_(None))
    )
    node = result.scalar_one_or_none()
    if node is None:
        return None
    if status is not None:
        node.status = status
    if node_name is not None:
        node.node_name = node_name
    await db.flush()
    await db.refresh(node)
    await db.commit()
    return node


async def delete_peer_node(db: AsyncSession, node_id: uuid.UUID) -> bool:
    """Soft-delete a peer node. Returns True on success, False if not found."""
    from datetime import datetime, timezone

    result = await db.execute(
        select(Node).where(Node.id == node_id, Node.deleted_at.is_(None))
    )
    node = result.scalar_one_or_none()
    if node is None:
        return False
    node.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()
    return True


# ─── Federated resource operations ───────────────────────────────────────────


async def upsert_federated_skill(db: AsyncSession, origin_node_id, body) -> tuple:
    """Upsert a federated Skill.

    ``body`` must expose: title, content, service_scope, stack, skill_type,
    lifecycle, version, external_id.
    Returns ``(skill_obj, created: bool)``.
    """
    existing = None
    if origin_node_id:
        result = await db.execute(
            select(Skill).where(
                Skill.origin_node_id == origin_node_id,
                Skill.title == body.title,
            )
        )
        existing = result.scalar_one_or_none()

    if existing:
        existing.content = body.content
        existing.service_scope = body.service_scope
        existing.stack = body.stack
        existing.lifecycle = body.lifecycle
        existing.version = body.version
        await db.flush()
        await db.refresh(existing)
        return existing, False

    skill = Skill(
        title=body.title,
        content=body.content,
        service_scope=body.service_scope,
        stack=body.stack,
        skill_type=body.skill_type,
        lifecycle=body.lifecycle,
        version=body.version,
        origin_node_id=origin_node_id,
        federation_scope="federated",
    )
    db.add(skill)
    await db.flush()
    await db.refresh(skill)
    return skill, True


async def upsert_federated_wiki(db: AsyncSession, origin_node_id, body) -> tuple:
    """Upsert a federated WikiArticle.

    ``body`` must expose: slug, title, content, tags, version.
    Returns ``(article_obj, created: bool)``.
    """
    existing = None
    if origin_node_id:
        result = await db.execute(
            select(WikiArticle).where(
                WikiArticle.origin_node_id == origin_node_id,
                WikiArticle.slug == body.slug,
            )
        )
        existing = result.scalar_one_or_none()

    if existing:
        existing.title = body.title
        existing.content = body.content
        existing.tags = body.tags
        existing.version = body.version
        await db.flush()
        await db.refresh(existing)
        return existing, False

    article = WikiArticle(
        title=body.title,
        slug=body.slug,
        content=body.content,
        tags=body.tags,
        version=body.version,
        origin_node_id=origin_node_id,
        federation_scope="federated",
    )
    db.add(article)
    await db.flush()
    await db.refresh(article)
    return article, True


async def create_federated_epic(db: AsyncSession, origin_node_id, body) -> tuple:
    """Create a federated Epic with its tasks.

    Returns ``(epic_obj, task_count: int)``.
    """
    from app.models.epic import Epic
    from app.models.task import Task
    from app.services.key_generator import next_epic_key, next_task_key

    epic_key = await next_epic_key(db)
    epic = Epic(
        epic_key=epic_key,
        external_id=body.external_id,
        title=body.title,
        description=body.description,
        priority=body.priority,
        dod_framework=body.definition_of_done,
        origin_node_id=origin_node_id,
        state="scoped",
    )
    db.add(epic)
    await db.flush()

    task_count = 0
    for task_spec in body.tasks:
        task_key = await next_task_key(db)
        task = Task(
            task_key=task_key,
            epic_id=epic.id,
            external_id=task_spec.external_id,
            title=task_spec.title,
            description=task_spec.description,
            state=task_spec.state or "incoming",
            definition_of_done=task_spec.definition_of_done,
            pinned_skills=task_spec.pinned_skills,
            assigned_node_id=task_spec.assigned_node_id,
        )
        db.add(task)
        task_count += 1

    await db.flush()
    await db.refresh(epic)
    return epic, task_count


async def find_and_update_federated_task(db: AsyncSession, origin_node_id, body):
    """Find a task by external_id/task_key and apply a federated state update.

    Returns the updated task object.
    Raises ``LookupError`` if not found, ``PermissionError`` if the requesting
    node is not authorised, ``ValueError`` on invalid state transitions.
    """
    from app.models.task import Task
    from app.services.state_machine import TASK_ALLOWED_TRANSITIONS

    result = await db.execute(
        select(Task).where(Task.external_id == body.external_id)
    )
    task = result.scalar_one_or_none()

    if task is None:
        result = await db.execute(
            select(Task).where(Task.task_key == body.external_id)
        )
        task = result.scalar_one_or_none()

    if task is None:
        raise LookupError(f"Task '{body.external_id}' not found")

    if task.assigned_node_id and origin_node_id:
        if task.assigned_node_id != origin_node_id:
            raise PermissionError("Only the assigned node can update this task")

    if body.state not in TASK_ALLOWED_TRANSITIONS.get(task.state, set()):
        raise ValueError(f"Invalid transition: {task.state} → {body.state}")

    task.state = body.state
    if body.result:
        task.result = body.result
    task.version += 1
    await db.flush()
    await db.refresh(task)
    return task
