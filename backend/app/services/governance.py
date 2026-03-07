"""Governance Levels Service — Phase 8 (TASK-8-006).

Governance types: review, epic_proposal, epic_scoping, skill_merge,
                  guard_merge, decision_request, escalation
Levels: manual | assisted | auto

Also provides Guard CRUD helpers (TASK-8 refactor).
"""
import json
import logging
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guard import Guard
from app.schemas.crud import GuardCreate, GuardUpdate
from app.services.guard_materialization import materialize_guard_for_existing_tasks

logger = logging.getLogger(__name__)

GOVERNANCE_TYPES = [
    "review",
    "epic_proposal",
    "epic_scoping",
    "skill_merge",
    "guard_merge",
    "decision_request",
    "escalation",
]

VALID_LEVELS = {"manual", "assisted", "auto"}

DEFAULT_GOVERNANCE = {t: "manual" for t in GOVERNANCE_TYPES}


async def get_governance(db: AsyncSession) -> dict[str, str]:
    """Return current governance config from app_settings."""
    from app.models.settings import AppSettings
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "governance")
    )
    row = result.scalar_one_or_none()
    if row is None:
        return DEFAULT_GOVERNANCE.copy()
    try:
        data = json.loads(row.value) if isinstance(row.value, str) else row.value
        # Merge with defaults to handle missing keys
        merged = DEFAULT_GOVERNANCE.copy()
        merged.update({k: v for k, v in data.items() if k in GOVERNANCE_TYPES and v in VALID_LEVELS})
        return merged
    except Exception:
        return DEFAULT_GOVERNANCE.copy()


async def update_governance(db: AsyncSession, updates: dict[str, str]) -> dict[str, str]:
    """Update governance config. Validates types and levels."""
    for key, value in updates.items():
        if key not in GOVERNANCE_TYPES:
            raise ValueError(f"Unknown governance type: {key}")
        if value not in VALID_LEVELS:
            raise ValueError(f"Invalid governance level: {value}. Must be manual|assisted|auto")

    current = await get_governance(db)
    current.update(updates)

    from app.models.settings import AppSettings
    result = await db.execute(
        select(AppSettings).where(AppSettings.key == "governance")
    )
    row = result.scalar_one_or_none()
    value_json = json.dumps(current)
    if row is None:
        db.add(AppSettings(key="governance", value=value_json))
    else:
        row.value = value_json
    await db.commit()
    return current


async def get_governance_level(db: AsyncSession, governance_type: str) -> str:
    """Get the current level for a specific governance type."""
    config = await get_governance(db)
    return config.get(governance_type, "manual")


# ── Guard CRUD ────────────────────────────────────────────────────────────────

async def get_guard_by_id(db: AsyncSession, guard_id: uuid.UUID) -> Guard | None:
    """Fetch a Guard by primary key."""
    result = await db.execute(select(Guard).where(Guard.id == guard_id))
    return result.scalar_one_or_none()


async def create_guard(db: AsyncSession, body: GuardCreate, actor: Any) -> Guard:
    """Create a new Guard and flush to DB."""
    guard = Guard(
        title=body.title,
        description=body.description,
        type=body.type,
        command=body.command,
        condition=body.condition,
        scope=body.scope,
        project_id=body.project_id,
        skill_id=body.skill_id,
        skippable=body.skippable,
        created_by=actor.id,
    )
    db.add(guard)
    await db.flush()
    await db.refresh(guard)
    return guard


async def update_guard_record(
    db: AsyncSession, guard_id: uuid.UUID, body: GuardUpdate, actor: Any
) -> Guard:
    """Update an existing Guard with optimistic locking."""
    guard = await get_guard_by_id(db, guard_id)
    if not guard:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guard nicht gefunden")

    if body.expected_version is not None and guard.version != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version-Conflict: erwartet {body.expected_version}, aktuell {guard.version}",
        )

    was_active = guard.lifecycle == "active"

    if body.title is not None:
        guard.title = body.title
    if body.description is not None:
        guard.description = body.description
    if body.type is not None:
        guard.type = body.type
    if body.command is not None:
        guard.command = body.command
    if body.condition is not None:
        guard.condition = body.condition
    if body.scope is not None:
        guard.scope = body.scope
    if body.skippable is not None:
        guard.skippable = body.skippable
    if body.lifecycle is not None:
        guard.lifecycle = body.lifecycle

    guard.version += 1
    await db.flush()
    if guard.lifecycle == "active" and (
        not was_active or body.scope is not None
    ):
        await materialize_guard_for_existing_tasks(db, guard)
    await db.refresh(guard)
    return guard

def is_auto(level: str) -> bool:
    return level == "auto"


def is_assisted(level: str) -> bool:
    return level == "assisted"


def is_manual(level: str) -> bool:
    return level == "manual"
