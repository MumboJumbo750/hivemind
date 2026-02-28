"""Settings-API + Task-Assignment (TASK-2-009).

GET  /api/settings         — aktuellen Modus + notification_mode lesen
PATCH /api/settings        — Modus umschalten (solo | team)
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.settings import AppSettings
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    mode: str
    notification_mode: str


class SettingsUpdate(BaseModel):
    mode: Literal["solo", "team"]


async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    result = await db.execute(select(AppSettings).where(AppSettings.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else default


@router.get("", response_model=SettingsResponse)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SettingsResponse:
    mode = await _get_setting(db, "hivemind_mode", "solo")
    notification_mode = await _get_setting(db, "notification_mode", "client")
    return SettingsResponse(mode=mode, notification_mode=notification_mode)


@router.patch("", response_model=SettingsResponse)
async def update_settings(
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SettingsResponse:
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "hivemind_mode")
    )
    row = result.scalar_one_or_none()
    if row:
        row.value = body.mode
        row.updated_by = actor.id
    else:
        db.add(AppSettings(key="hivemind_mode", value=body.mode, updated_by=actor.id))

    await db.flush()
    # _get_app_mode in deps.py liest bei jedem Request frisch aus der DB → kein Cache nötig

    notification_mode = await _get_setting(db, "notification_mode", "client")
    return SettingsResponse(mode=body.mode, notification_mode=notification_mode)
