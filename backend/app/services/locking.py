"""Optimistic Locking + Idempotenz-Utilities (TASK-2-005)."""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import IdempotencyKey


async def check_idempotency(
    db: AsyncSession,
    idempotency_key: uuid.UUID,
    actor_id: uuid.UUID,
    tool_name: str,
) -> dict | None:
    """Gibt response_body zurück wenn Key bereits completed existiert, sonst None.

    Fenster: 24h (über expires_at Spalte).
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(IdempotencyKey).where(
            IdempotencyKey.key == idempotency_key,
            IdempotencyKey.status == "completed",
            IdempotencyKey.expires_at > now,
        )
    )
    existing = result.scalar_one_or_none()
    return existing.response_body if existing else None


async def save_idempotency_result(
    db: AsyncSession,
    idempotency_key: uuid.UUID,
    actor_id: uuid.UUID,
    tool_name: str,
    response_status: int,
    response_body: Any,
) -> None:
    """Speichert oder aktualisiert den Idempotency-Eintrag als completed."""
    from datetime import timedelta
    from sqlalchemy.dialects.postgresql import insert

    expires = datetime.now(timezone.utc) + timedelta(hours=24)

    # Upsert — bei Race-Condition bleibt der erste Eintrag bestehen (UNIQUE constraint)
    stmt = insert(IdempotencyKey).values(
        key=idempotency_key,
        actor_id=actor_id,
        tool_name=tool_name,
        status="completed",
        response_status=response_status,
        response_body=response_body,
        expires_at=expires,
    ).on_conflict_do_update(
        index_elements=["key"],
        set_={"status": "completed", "response_status": response_status, "response_body": response_body},
    )
    await db.execute(stmt)


def check_version(entity: Any, expected_version: int) -> None:
    """HTTP 409 wenn entity.version != expected_version."""
    if entity.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Version-Konflikt: erwartet {expected_version}, "
                f"aktuell {entity.version}. Bitte Entity neu laden."
            ),
        )
