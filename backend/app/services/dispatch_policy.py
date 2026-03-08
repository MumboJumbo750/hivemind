"""Dispatch Policy Service — per-role execution policies with safe defaults.

Provides:
  - EffectivePolicy dataclass — all policy fields resolved (DB overrides + defaults)
  - DEFAULT_POLICIES — conservative built-in policies for all known agent roles
  - get_effective_policy()  — DB lookup merged with defaults; never raises
  - count_active_dispatches() — active dispatch count for parallelism gate
  - get_all_policies_with_status() — operator view of all roles
  - SkipReason — structured string constants for dispatch skip/fallback reasons
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skip-reason constants (stored in conductor_dispatches.result)
# ---------------------------------------------------------------------------


class SkipReason:
    COOLDOWN_ACTIVE = "cooldown_active"
    PARALLEL_LIMIT_EXCEEDED = "parallel_limit_exceeded"
    POLICY_DISABLED = "policy_disabled"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    CONDUCTOR_DISABLED = "conductor_disabled"
    BYOAI_FALLBACK = "byoai_fallback"
    LOCAL_ERROR_FALLBACK = "local_error_fallback"


# ---------------------------------------------------------------------------
# EffectivePolicy dataclass
# ---------------------------------------------------------------------------


@dataclass
class EffectivePolicy:
    """Resolved dispatch policy for a single agent role."""

    agent_role: str
    preferred_execution_mode: str = "local"
    fallback_chain: list[str] = field(default_factory=lambda: ["local", "byoai"])
    rpm_limit: int = 5
    token_budget: int = 4000
    max_parallel: int = 1
    cooldown_seconds: int = 30
    enabled: bool = True
    source: str = "default"  # "db" | "default"

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_role": self.agent_role,
            "preferred_execution_mode": self.preferred_execution_mode,
            "fallback_chain": self.fallback_chain,
            "rpm_limit": self.rpm_limit,
            "token_budget": self.token_budget,
            "max_parallel": self.max_parallel,
            "cooldown_seconds": self.cooldown_seconds,
            "enabled": self.enabled,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Built-in defaults — conservative, safe values per agent role
# ---------------------------------------------------------------------------

_DEFAULT_POLICIES: dict[str, EffectivePolicy] = {
    "worker": EffectivePolicy(
        agent_role="worker",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=10,
        token_budget=8000,
        max_parallel=2,
        cooldown_seconds=10,
    ),
    "reviewer": EffectivePolicy(
        agent_role="reviewer",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=5,
        token_budget=4000,
        max_parallel=1,
        cooldown_seconds=30,
    ),
    "gaertner": EffectivePolicy(
        agent_role="gaertner",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=5,
        token_budget=8000,
        max_parallel=1,
        cooldown_seconds=60,
    ),
    "kartograph": EffectivePolicy(
        agent_role="kartograph",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=5,
        token_budget=8000,
        max_parallel=1,
        cooldown_seconds=120,
    ),
    "architekt": EffectivePolicy(
        agent_role="architekt",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=5,
        token_budget=8000,
        max_parallel=1,
        cooldown_seconds=60,
    ),
    "stratege": EffectivePolicy(
        agent_role="stratege",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=3,
        token_budget=8000,
        max_parallel=1,
        cooldown_seconds=120,
    ),
    "triage": EffectivePolicy(
        agent_role="triage",
        preferred_execution_mode="local",
        fallback_chain=["local", "byoai"],
        rpm_limit=10,
        token_budget=4000,
        max_parallel=2,
        cooldown_seconds=5,
    ),
}


def get_default_policy(agent_role: str) -> EffectivePolicy:
    """Return built-in default policy; unknown roles get a conservative safe default."""
    return _DEFAULT_POLICIES.get(agent_role, EffectivePolicy(agent_role=agent_role))


# ---------------------------------------------------------------------------
# DB lookup
# ---------------------------------------------------------------------------


async def get_effective_policy(agent_role: str, db: Any) -> EffectivePolicy:
    """Load the effective policy for agent_role from DB, merging with defaults.

    Never raises — falls back to the safe default on any error.
    """
    from sqlalchemy import select

    from app.models.dispatch_policy import AgentDispatchPolicy

    default = get_default_policy(agent_role)
    row = None
    try:
        result = await db.execute(
            select(AgentDispatchPolicy).where(AgentDispatchPolicy.agent_role == agent_role)
        )
        row = result.scalar_one_or_none()
    except Exception:
        logger.debug("dispatch_policy: DB lookup failed for role '%s', using defaults", agent_role)
        return default

    if row is None:
        return default

    chain = row.fallback_chain
    if not isinstance(chain, list) or not chain:
        chain = default.fallback_chain

    return EffectivePolicy(
        agent_role=agent_role,
        preferred_execution_mode=row.preferred_execution_mode or default.preferred_execution_mode,
        fallback_chain=chain,
        rpm_limit=row.rpm_limit if row.rpm_limit is not None else default.rpm_limit,
        token_budget=row.token_budget if row.token_budget is not None else default.token_budget,
        max_parallel=row.max_parallel if row.max_parallel is not None else default.max_parallel,
        cooldown_seconds=(
            row.cooldown_seconds if row.cooldown_seconds is not None else default.cooldown_seconds
        ),
        enabled=row.enabled,
        source="db",
    )


async def count_active_dispatches(agent_role: str, db: Any) -> int:
    """Count dispatches currently in 'running' or 'dispatched' state for this role.

    Used for per-role parallelism enforcement. Returns 0 on any error.
    """
    from sqlalchemy import func, select

    from app.models.conductor import ConductorDispatch

    try:
        result = await db.execute(
            select(func.count()).where(
                ConductorDispatch.agent_role == agent_role,
                ConductorDispatch.status.in_(["running", "dispatched"]),
            )
        )
        return result.scalar() or 0
    except Exception:
        logger.debug("dispatch_policy: active count query failed for role '%s'", agent_role)
        return 0


# ---------------------------------------------------------------------------
# Operator view
# ---------------------------------------------------------------------------


async def get_all_policies_with_status(db: Any) -> list[dict[str, Any]]:
    """Return all known roles with their effective policy and current dispatch status."""
    from sqlalchemy import select

    from app.models.dispatch_policy import AgentDispatchPolicy

    known_roles = set(_DEFAULT_POLICIES.keys())
    try:
        result = await db.execute(select(AgentDispatchPolicy))
        db_rows = {row.agent_role for row in result.scalars().all()}
        known_roles |= db_rows
    except Exception:
        pass

    out = []
    for role in sorted(known_roles):
        policy = await get_effective_policy(role, db)
        active = await count_active_dispatches(role, db)
        out.append(
            {
                **policy.as_dict(),
                "active_dispatches": active,
                "at_limit": active >= policy.max_parallel,
            }
        )
    return out


async def upsert_policy(agent_role: str, updates: dict[str, Any], db: Any) -> EffectivePolicy:
    """Create or update the DB policy row for agent_role."""
    import uuid

    from sqlalchemy import select

    from app.models.dispatch_policy import AgentDispatchPolicy

    result = await db.execute(
        select(AgentDispatchPolicy).where(AgentDispatchPolicy.agent_role == agent_role)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = AgentDispatchPolicy(
            id=uuid.uuid4(),
            agent_role=agent_role,
        )
        db.add(row)

    for key, value in updates.items():
        if hasattr(row, key) and key not in ("id", "agent_role"):
            setattr(row, key, value)
    row.updated_at = datetime.now(UTC)
    await db.flush()
    return await get_effective_policy(agent_role, db)


async def delete_policy(agent_role: str, db: Any) -> bool:
    """Delete the DB override for agent_role (reverts to defaults). Returns True if deleted."""
    from sqlalchemy import select

    from app.models.dispatch_policy import AgentDispatchPolicy

    result = await db.execute(
        select(AgentDispatchPolicy).where(AgentDispatchPolicy.agent_role == agent_role)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True
