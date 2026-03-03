"""Governance Levels Service — Phase 8 (TASK-8-006).

Governance types: review, epic_proposal, epic_scoping, skill_merge,
                  guard_merge, decision_request, escalation
Levels: manual | assisted | auto
"""
import json
import logging
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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


def is_auto(level: str) -> bool:
    return level == "auto"


def is_assisted(level: str) -> bool:
    return level == "assisted"


def is_manual(level: str) -> bool:
    return level == "manual"
