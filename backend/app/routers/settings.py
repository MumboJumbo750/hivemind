"""Settings-API + Task-Assignment (TASK-2-009).

GET  /api/settings                       — aktuellen Modus + notification_mode lesen
PATCH /api/settings                      — Modus umschalten (solo | team)
GET  /api/settings/routing-threshold     — Routing-Threshold lesen (TASK-7-007)
PATCH /api/settings/routing-threshold    — Routing-Threshold setzen (TASK-7-007)
GET  /api/settings/routing_threshold     — Alias (DoD/compat)
PATCH /api/settings/routing_threshold    — Alias (DoD/compat)
"""
from datetime import UTC, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import has_routing_threshold_env_override, settings
from app.db import get_db
from app.models.settings import AppSettings
from app.routers.deps import get_current_actor, require_role
from app.schemas.auth import CurrentActor
from app.services.audit import write_audit

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


# ── Routing-Threshold (TASK-7-007) ────────────────────────────────────────────

class RoutingThresholdResponse(BaseModel):
    current_value: float
    source: Literal["env", "db"]
    last_updated: Optional[datetime] = None
    updated_by: Optional[str] = None


class RoutingThresholdUpdate(BaseModel):
    value: float = Field(..., ge=0.0, le=1.0, description="Threshold between 0.0 and 1.0")


@router.get("/routing-threshold", response_model=RoutingThresholdResponse)
@router.get("/routing_threshold", response_model=RoutingThresholdResponse, include_in_schema=False)
async def get_routing_threshold(
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> RoutingThresholdResponse:
    del actor
    # If env var is explicitly set, report env source (even if value equals default).
    if has_routing_threshold_env_override():
        return RoutingThresholdResponse(
            current_value=settings.hivemind_routing_threshold,
            source="env",
        )

    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "routing_threshold")
    )
    row = result.scalar_one_or_none()
    if row:
        try:
            value = float(row.value)
        except (ValueError, TypeError):
            value = 0.85
        return RoutingThresholdResponse(
            current_value=value,
            source="db",
            last_updated=row.updated_at,
            updated_by=str(row.updated_by) if row.updated_by else None,
        )

    return RoutingThresholdResponse(current_value=0.85, source="db")


@router.patch("/routing-threshold", response_model=RoutingThresholdResponse)
@router.patch("/routing_threshold", response_model=RoutingThresholdResponse, include_in_schema=False)
async def update_routing_threshold(
    body: RoutingThresholdUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin")),
) -> RoutingThresholdResponse:
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "routing_threshold")
    )
    row = result.scalar_one_or_none()
    new_value_str = str(body.value)

    if row:
        row.value = new_value_str
        row.updated_by = actor.id
        row.updated_at = datetime.now(UTC)
    else:
        db.add(
            AppSettings(
                key="routing_threshold",
                value=new_value_str,
                updated_by=actor.id,
                updated_at=datetime.now(UTC),
            )
        )

    await db.flush()

    await write_audit(
        tool_name="update_routing_threshold",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"new_value": body.value},
    )

    # Invalidate the in-memory cache in routing_service
    from app.services.routing_service import invalidate_threshold_cache
    invalidate_threshold_cache()

    result2 = await db.execute(
        select(AppSettings).where(AppSettings.key == "routing_threshold")
    )
    updated = result2.scalar_one_or_none()
    return RoutingThresholdResponse(
        current_value=body.value,
        source="db",
        last_updated=updated.updated_at if updated else None,
        updated_by=str(actor.id),
    )
