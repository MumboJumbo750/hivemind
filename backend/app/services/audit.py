"""Audit-Writer — non-blocking Write-Log in mcp_invocations (TASK-2-006).

Verwendung als Decorator auf mutierenden Endpoints:

    @router.patch("/{id}")
    @audit_write("update_epic")
    async def update_epic(...):
        ...

Oder als direkter Aufruf nach dem Write:

    await write_audit(db, actor, tool_name="update_task", ...)
"""
import asyncio
import logging
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import McpInvocation

logger = logging.getLogger(__name__)


async def write_audit(
    tool_name: str,
    actor_id: uuid.UUID,
    actor_role: str,
    input_payload: dict | None = None,
    output_payload: dict | None = None,
    epic_id: uuid.UUID | None = None,
    target_id: str | None = None,
    idempotency_key: uuid.UUID | None = None,
    duration_ms: int | None = None,
) -> None:
    """Schreibt Audit-Eintrag non-blocking in einer eigenen Session."""

    async def _write() -> None:
        try:
            from app.db import AsyncSessionLocal as _SessionLocal

            async with _SessionLocal() as session:
                invocation = McpInvocation(
                    request_id=uuid.uuid4(),
                    idempotency_key=idempotency_key,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    tool_name=tool_name,
                    epic_id=epic_id,
                    target_id=target_id,
                    input_payload=input_payload,
                    output_payload=output_payload,
                    duration_ms=duration_ms,
                    status="completed",
                )
                session.add(invocation)
                await session.commit()
        except Exception:
            logger.exception("Audit-Write fehlgeschlagen (non-critical)")

    asyncio.create_task(_write())


async def write_audit_sync(
    db: AsyncSession,
    tool_name: str,
    actor_id: uuid.UUID,
    actor_role: str,
    input_payload: dict | None = None,
    output_payload: dict | None = None,
    epic_id: uuid.UUID | None = None,
    target_id: str | None = None,
    idempotency_key: uuid.UUID | None = None,
    duration_ms: int | None = None,
) -> None:
    """Schreibt Audit-Eintrag in der bestehenden DB-Session (für Tests und direkte Calls)."""
    invocation = McpInvocation(
        request_id=uuid.uuid4(),
        idempotency_key=idempotency_key,
        actor_id=actor_id,
        actor_role=actor_role,
        tool_name=tool_name,
        epic_id=epic_id,
        target_id=target_id,
        input_payload=input_payload,
        output_payload=output_payload,
        duration_ms=duration_ms,
        status="completed",
    )
    db.add(invocation)
    await db.flush()


async def query_invocations(
    db: AsyncSession,
    *,
    own_actor_id: uuid.UUID | None = None,
    actor_role: str = "developer",
    actor_id_filter: uuid.UUID | None = None,
    tool_name: str | None = None,
    entity_type: str | None = None,
    target_id: str | None = None,
    from_date=None,
    to_date=None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list, int]:
    """Gibt (entries, total) mit RBAC zurück. developer sieht nur eigene Einträge."""
    from sqlalchemy import func, select as _select

    base = _select(McpInvocation)
    if actor_role not in ("admin", "triage") and own_actor_id is not None:
        base = base.where(McpInvocation.actor_id == own_actor_id)
    if actor_id_filter:
        base = base.where(McpInvocation.actor_id == actor_id_filter)
    if tool_name:
        base = base.where(McpInvocation.tool_name == tool_name)
    if target_id:
        base = base.where(McpInvocation.target_id == target_id)
    if entity_type:
        base = base.where(McpInvocation.tool_name.ilike(f"%{entity_type}%"))
    if from_date:
        base = base.where(McpInvocation.created_at >= from_date)
    if to_date:
        base = base.where(McpInvocation.created_at <= to_date)

    count_q = _select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    offset = (page - 1) * page_size
    query = base.order_by(McpInvocation.created_at.desc()).limit(page_size).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def resolve_usernames(
    db: AsyncSession, user_ids: "set[uuid.UUID]"
) -> "dict[uuid.UUID, str]":
    """Gibt {user_id: username} für die gegebenen IDs zurück."""
    from app.models.user import User
    from sqlalchemy import select as _select

    if not user_ids:
        return {}
    result = await db.execute(_select(User).where(User.id.in_(user_ids)))
    return {u.id: u.username for u in result.scalars().all()}
