"""Helpers for assisted governance gates and recommendation persistence."""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance_recommendation import GovernanceRecommendation


GOVERNED_PROMPTS: dict[str, dict[str, Any]] = {
    "triage_epic_proposal": {
        "governance_type": "epic_proposal",
        "target_type": "epic_proposal",
        "decisive_tools": {
            "hivemind-accept_epic_proposal",
            "hivemind-reject_epic_proposal",
        },
    },
    "triage_skill_proposal": {
        "governance_type": "skill_merge",
        "target_type": "skill",
        "decisive_tools": {
            "hivemind-merge_skill",
            "hivemind-reject_skill",
            "hivemind-accept_skill_change",
            "hivemind-reject_skill_change",
        },
    },
    "triage_guard_proposal": {
        "governance_type": "guard_merge",
        "target_type": "guard",
        "decisive_tools": {
            "hivemind-merge_guard",
            "hivemind-reject_guard",
        },
    },
    "triage_decision_request": {
        "governance_type": "decision_request",
        "target_type": "decision_request",
        "decisive_tools": {
            "hivemind-resolve_decision_request",
        },
    },
    "triage_escalation": {
        "governance_type": "escalation",
        "target_type": "task",
        "decisive_tools": {
            "hivemind-resolve_escalation",
            "hivemind-reassign_epic_owner",
        },
    },
    "architekt_decompose": {
        "governance_type": "epic_scoping",
        "target_type": "epic",
        "decisive_tools": {
            "hivemind-decompose_epic",
            "hivemind-create_task",
            "hivemind-create_subtask",
            "hivemind-link_skill",
            "hivemind-set_context_boundary",
            "hivemind-assign_task",
            "hivemind-update_task_state",
        },
    },
}


_ACTION_HINTS: dict[str, list[tuple[str, str]]] = {
    "epic_proposal": [
        (r"\baccept", "accept"),
        (r"\breject", "reject"),
    ],
    "skill_merge": [
        (r"\bmerge", "merge"),
        (r"\breject", "reject"),
    ],
    "guard_merge": [
        (r"\bmerge", "merge"),
        (r"\breject", "reject"),
    ],
    "decision_request": [
        (r"\bresolve", "resolve"),
        (r"\bchoose", "resolve"),
    ],
    "escalation": [
        (r"\bresolve", "resolve"),
        (r"\breassign", "reassign"),
    ],
    "epic_scoping": [
        (r"\bdecompose", "decompose"),
        (r"\bscope", "scope"),
    ],
}


def get_governed_prompt(prompt_type: str) -> dict[str, Any] | None:
    return GOVERNED_PROMPTS.get(prompt_type)


def decisive_tools_for_prompt(prompt_type: str) -> set[str]:
    prompt = get_governed_prompt(prompt_type)
    return set(prompt["decisive_tools"]) if prompt else set()


def infer_recommended_action(governance_type: str, content: str | None) -> str | None:
    text = (content or "").strip().lower()
    if not text:
        return None
    for pattern, action in _ACTION_HINTS.get(governance_type, []):
        if re.search(pattern, text):
            return action
    return "recommend"


def build_recommendation_fingerprint(
    *,
    governance_type: str,
    target_type: str,
    target_ref: str,
    action: str | None,
    rationale: str | None,
) -> str:
    raw = "|".join(
        [
            governance_type,
            target_type,
            target_ref,
            action or "",
            (rationale or "").strip(),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def store_governance_recommendation(
    db: AsyncSession,
    *,
    governance_type: str,
    governance_level: str,
    target_type: str,
    target_ref: str,
    agent_role: str,
    prompt_type: str,
    rationale: str | None,
    action: str | None,
    dispatch_id: str | None,
    payload: dict[str, Any] | None = None,
    confidence: float | None = None,
    status: str = "pending_human",
) -> GovernanceRecommendation | None:
    fingerprint = build_recommendation_fingerprint(
        governance_type=governance_type,
        target_type=target_type,
        target_ref=target_ref,
        action=action,
        rationale=rationale,
    )
    try:
        existing = (
            await db.execute(
                select(GovernanceRecommendation).where(
                    GovernanceRecommendation.fingerprint == fingerprint
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        recommendation = GovernanceRecommendation(
            id=uuid.uuid4(),
            governance_type=governance_type,
            governance_level=governance_level,
            target_type=target_type,
            target_ref=target_ref,
            status=status,
            agent_role=agent_role,
            prompt_type=prompt_type,
            action=action,
            confidence=confidence,
            rationale=rationale,
            payload=payload,
            fingerprint=fingerprint,
            dispatch_id=uuid.UUID(dispatch_id) if dispatch_id else None,
            created_at=datetime.now(UTC),
        )
        db.add(recommendation)
        await db.flush()
        return recommendation
    except Exception:
        return None
