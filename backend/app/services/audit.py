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
