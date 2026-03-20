"""Governance Levels Service — Phase 8 (TASK-8-006).

Governance types: review, epic_proposal, epic_scoping, skill_merge,
                  guard_merge, decision_request, escalation
Levels: manual | assisted | auto

Also provides Guard CRUD helpers (TASK-8 refactor).
"""
from datetime import UTC, datetime, timedelta
import json
import logging
import uuid
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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


def get_governance_auto_promotion_config() -> dict[str, Any]:
    """Return normalized auto-promotion settings for review governance."""
    min_consecutive = max(int(settings.hivemind_governance_auto_promotion_min_consecutive_approves), 1)
    min_confidence = float(settings.hivemind_governance_auto_promotion_min_confidence)
    evaluation_window_days = max(int(settings.hivemind_governance_auto_promotion_evaluation_window_days), 1)
    return {
        "enabled": bool(settings.hivemind_governance_auto_promotion_enabled),
        "min_consecutive_approves": min_consecutive,
        "min_confidence": min(max(min_confidence, 0.0), 1.0),
        "evaluation_window_days": evaluation_window_days,
    }


def _decode_governance_value(raw_value: Any) -> dict[str, str]:
    try:
        data = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        merged = DEFAULT_GOVERNANCE.copy()
        merged.update(
            {k: v for k, v in data.items() if k in GOVERNANCE_TYPES and v in VALID_LEVELS}
        )
        return merged
    except Exception:
        return DEFAULT_GOVERNANCE.copy()


async def _get_governance_row(db: AsyncSession) -> Any | None:
    from app.models.settings import AppSettings

    result = await db.execute(select(AppSettings).where(AppSettings.key == "governance"))
    return result.scalar_one_or_none()


async def _persist_governance(
    db: AsyncSession,
    values: dict[str, str],
    *,
    row: Any | None,
) -> dict[str, str]:
    from app.models.settings import AppSettings

    value_json = json.dumps(values)
    if row is None:
        db.add(AppSettings(key="governance", value=value_json))
    else:
        row.value = value_json
    await db.flush()
    return values


async def _notify_admins_about_governance_change(
    db: AsyncSession,
    *,
    notification_type: str,
    governance_type: str,
    from_level: str,
    to_level: str,
    reason: str,
) -> None:
    from app.services.notification_service import get_admin_user_ids, notify_users

    admin_ids = await get_admin_user_ids(db)
    if not admin_ids:
        return

    await notify_users(
        db,
        user_ids=admin_ids,
        notification_type=notification_type,
        body=(
            f"Governance '{governance_type}' wurde automatisch von '{from_level}' auf "
            f"'{to_level}' gesetzt. Grund: {reason}"
        ),
        entity_type="setting",
        entity_id=f"governance:{governance_type}",
        link="/settings/governance",
    )


async def get_governance(db: AsyncSession) -> dict[str, str]:
    """Return current governance config from app_settings."""
    row = await _get_governance_row(db)
    if row is None:
        return DEFAULT_GOVERNANCE.copy()
    return _decode_governance_value(row.value)


async def update_governance(db: AsyncSession, updates: dict[str, str]) -> dict[str, str]:
    """Update governance config. Validates types and levels."""
    for key, value in updates.items():
        if key not in GOVERNANCE_TYPES:
            raise ValueError(f"Unknown governance type: {key}")
        if value not in VALID_LEVELS:
            raise ValueError(f"Invalid governance level: {value}. Must be manual|assisted|auto")

    row = await _get_governance_row(db)
    current = _decode_governance_value(row.value) if row is not None else DEFAULT_GOVERNANCE.copy()
    current.update(updates)

    await _persist_governance(db, current, row=row)
    await db.commit()
    return current


async def get_governance_level(db: AsyncSession, governance_type: str) -> str:
    """Get the current level for a specific governance type."""
    config = await get_governance(db)
    return config.get(governance_type, "manual")


async def maybe_auto_promote_review_governance(db: AsyncSession) -> bool:
    """Promote review governance from assisted to auto when the streak qualifies."""
    from app.models.review import ReviewRecommendation

    config = get_governance_auto_promotion_config()
    if not config["enabled"]:
        return False

    row = await _get_governance_row(db)
    current = _decode_governance_value(row.value) if row is not None else DEFAULT_GOVERNANCE.copy()
    if current.get("review") != "assisted":
        return False

    cutoff = datetime.now(UTC) - timedelta(days=int(config["evaluation_window_days"]))
    result = await db.execute(
        select(ReviewRecommendation)
        .where(ReviewRecommendation.created_at >= cutoff)
        .order_by(ReviewRecommendation.created_at.desc())
        .limit(int(config["min_consecutive_approves"]))
    )
    recommendations = list(result.scalars().all())
    if len(recommendations) < int(config["min_consecutive_approves"]):
        return False

    qualified = 0
    min_confidence = float(config["min_confidence"])
    for recommendation in recommendations:
        if recommendation.recommendation != "approve":
            break
        if recommendation.vetoed_at is not None:
            break
        if recommendation.confidence is None or recommendation.confidence < min_confidence:
            break
        qualified += 1

    if qualified < int(config["min_consecutive_approves"]):
        return False

    current["review"] = "auto"
    await _persist_governance(db, current, row=row)
    await _notify_admins_about_governance_change(
        db,
        notification_type="governance_promoted",
        governance_type="review",
        from_level="assisted",
        to_level="auto",
        reason=(
            f"{qualified} konsekutive Approve-Empfehlungen mit Confidence >= "
            f"{min_confidence:.2f} in den letzten {int(config['evaluation_window_days'])} Tagen"
        ),
    )
    logger.info(
        "Governance auto-promotion applied for review: %s consecutive approves (min_confidence=%.2f, window=%sd)",
        qualified,
        min_confidence,
        int(config["evaluation_window_days"]),
    )
    return True


async def maybe_auto_demote_review_governance(db: AsyncSession) -> bool:
    """Demote review governance from auto to assisted after a veto."""
    config = get_governance_auto_promotion_config()
    if not config["enabled"]:
        return False

    row = await _get_governance_row(db)
    current = _decode_governance_value(row.value) if row is not None else DEFAULT_GOVERNANCE.copy()
    if current.get("review") != "auto":
        return False

    current["review"] = "assisted"
    await _persist_governance(db, current, row=row)
    await _notify_admins_about_governance_change(
        db,
        notification_type="governance_demoted",
        governance_type="review",
        from_level="auto",
        to_level="assisted",
        reason="Veto einer laufenden Auto-Review-Empfehlung",
    )
    logger.info("Governance auto-promotion demoted review governance back to assisted after veto")
    return True


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
