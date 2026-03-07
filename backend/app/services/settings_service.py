"""Settings-Service — AppSettings DB operations.

Centralises all direct DB access to the `app_settings` table,
so that routers never need to import `app.models.settings` directly.
"""
from datetime import UTC, datetime
from typing import Optional
import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.settings import AppSettings


async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    """Return the value for the given settings key, or *default* if not found."""
    result = await db.execute(select(AppSettings).where(AppSettings.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


async def get_setting_row(db: AsyncSession, key: str) -> Optional[AppSettings]:
    """Return the raw AppSettings row for *key*, or None."""
    result = await db.execute(select(AppSettings).where(AppSettings.key == key))
    return result.scalar_one_or_none()


async def upsert_setting(
    db: AsyncSession,
    key: str,
    value: str,
    updated_by: Optional[_uuid.UUID] = None,
) -> AppSettings:
    """Create or update a settings row. Does NOT commit — caller must flush/commit."""
    row = await get_setting_row(db, key)
    if row:
        row.value = value
        if updated_by is not None:
            row.updated_by = updated_by
        row.updated_at = datetime.now(UTC)
    else:
        row = AppSettings(key=key, value=value, updated_by=updated_by)
        db.add(row)
    return row
