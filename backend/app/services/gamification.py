"""Gamification Service — TASK-5-016.

EXP triggers, badge checks, and level-up logic.

EXP awards:
- task_done: +50 EXP
- guard_merged: +30 EXP  
- skill_accepted: +20 EXP
- decision_resolved: +15 EXP
- wiki_article_created: +10 EXP

Anti-spam: 1x per entity (tracked via exp_log in user record).
Level formula: level = exp_points // 100 + 1
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.event_bus import publish

logger = logging.getLogger(__name__)

# EXP values per trigger
EXP_TABLE = {
    "task_done": 50,
    "guard_merged": 30,
    "skill_accepted": 20,
    "decision_resolved": 15,
    "wiki_article_created": 10,
}

# Level titles
LEVEL_TITLES = {
    1: "Drone",
    2: "Worker Bee",
    3: "Scout",
    4: "Builder",
    5: "Engineer",
    6: "Architect",
    7: "Strategist",
    8: "Queen's Guard",
    9: "Hive Master",
    10: "Overmind",
}

# Badge definitions
BADGES = [
    {"key": "first_task", "title": "First Blood", "condition": lambda stats: stats.get("tasks_done", 0) >= 1},
    {"key": "ten_tasks", "title": "Decathlon", "condition": lambda stats: stats.get("tasks_done", 0) >= 10},
    {"key": "guard_master", "title": "Guard Master", "condition": lambda stats: stats.get("guards_merged", 0) >= 5},
    {"key": "skill_gardener", "title": "Skill Gardener", "condition": lambda stats: stats.get("skills_accepted", 0) >= 3},
    {"key": "wiki_author", "title": "Wiki Author", "condition": lambda stats: stats.get("wiki_articles", 0) >= 5},
    {"key": "level_5", "title": "Mid-Game", "condition": lambda stats: stats.get("level", 1) >= 5},
    {"key": "level_10", "title": "Endgame", "condition": lambda stats: stats.get("level", 1) >= 10},
]


def get_level(exp: int) -> int:
    """Calculate level from EXP points."""
    return max(1, exp // 100 + 1)


def get_level_title(level: int) -> str:
    """Get the title for a level."""
    return LEVEL_TITLES.get(min(level, 10), f"Level {level}")


async def award_exp(
    db: AsyncSession,
    user_id: uuid.UUID,
    trigger: str,
    entity_key: str,
) -> dict:
    """Award EXP for a trigger, with anti-spam (1x per entity).

    Returns dict with exp_awarded, new_exp, level, level_up, badges_earned.
    """
    from app.models.user import User

    amount = EXP_TABLE.get(trigger, 0)
    if not amount:
        return {"exp_awarded": 0, "reason": f"Unknown trigger: {trigger}"}

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return {"exp_awarded": 0, "reason": "User not found"}

        # Anti-spam: check notification_preferences for exp_log
        exp_log = (user.notification_preferences or {}).get("exp_log", [])
        for entry in exp_log:
            if entry.get("trigger") == trigger and entry.get("entity") == entity_key:
                return {"exp_awarded": 0, "reason": "Already awarded"}

        # Award EXP
        old_exp = user.exp_points or 0
        old_level = get_level(old_exp)
        new_exp = old_exp + amount
        new_level = get_level(new_exp)

        user.exp_points = new_exp

        # Log the award
        log_entry = {
            "trigger": trigger,
            "entity": entity_key,
            "amount": amount,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        prefs = user.notification_preferences or {}
        prefs["exp_log"] = exp_log + [log_entry]
        user.notification_preferences = prefs

        await db.flush()

        result_data = {
            "exp_awarded": amount,
            "new_exp": new_exp,
            "level": new_level,
            "level_title": get_level_title(new_level),
            "level_up": new_level > old_level,
            "badges_earned": [],
        }

        # Check level-up
        if new_level > old_level:
            await publish(
                "level_up",
                {
                    "user_id": str(user_id),
                    "level": new_level,
                    "title": get_level_title(new_level),
                    "exp": new_exp,
                },
                channel="gamification",
            )

        # Check badges
        stats = _compute_stats(prefs.get("exp_log", []))
        stats["level"] = new_level
        earned_badges = prefs.get("badges", [])
        for badge in BADGES:
            if badge["key"] not in earned_badges and badge["condition"](stats):
                earned_badges.append(badge["key"])
                result_data["badges_earned"].append(badge["title"])
                await publish(
                    "badge_earned",
                    {
                        "user_id": str(user_id),
                        "badge": badge["key"],
                        "title": badge["title"],
                    },
                    channel="gamification",
                )

        prefs["badges"] = earned_badges
        user.notification_preferences = prefs
        await db.flush()

        return result_data

    except Exception:
        logger.exception("award_exp failed")
        return {"exp_awarded": 0, "reason": "Internal error"}


def _compute_stats(exp_log: list[dict]) -> dict:
    """Compute achievement stats from exp_log."""
    stats = {
        "tasks_done": 0,
        "guards_merged": 0,
        "skills_accepted": 0,
        "wiki_articles": 0,
    }
    for entry in exp_log:
        trigger = entry.get("trigger", "")
        if trigger == "task_done":
            stats["tasks_done"] += 1
        elif trigger == "guard_merged":
            stats["guards_merged"] += 1
        elif trigger == "skill_accepted":
            stats["skills_accepted"] += 1
        elif trigger == "wiki_article_created":
            stats["wiki_articles"] += 1
    return stats


async def get_user_achievements(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Get user's gamification status."""
    from app.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return {"error": "User not found"}

    exp = user.exp_points or 0
    level = get_level(exp)
    prefs = user.notification_preferences or {}
    badges = prefs.get("badges", [])
    exp_log = prefs.get("exp_log", [])

    return {
        "user_id": str(user_id),
        "exp": exp,
        "level": level,
        "level_title": get_level_title(level),
        "next_level_exp": level * 100,
        "exp_to_next": max(0, level * 100 - exp),
        "badges": badges,
        "recent_exp": exp_log[-10:] if exp_log else [],
    }
