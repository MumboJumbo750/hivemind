"""Dispatch Policies API — TASK-AGENT-003.

Operator endpoints for inspecting and managing per-role dispatch policies.

GET  /api/dispatch/policies         — list all policies with real-time status
GET  /api/dispatch/policies/status  — real-time per-role status (active dispatches, at_limit, last skip)
GET  /api/dispatch/policies/{role}  — single role policy
PUT  /api/dispatch/policies/{role}  — upsert policy override
DELETE /api/dispatch/policies/{role} — reset role to safe defaults
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_user

router = APIRouter(prefix="/dispatch/policies", tags=["dispatch-policies"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PolicyUpsertRequest(BaseModel):
    preferred_execution_mode: str | None = Field(
        None, description="Preferred execution mode: local | ide | github_actions | byoai"
    )
    fallback_chain: list[str] | None = Field(
        None, description="Ordered fallback chain, e.g. ['local', 'byoai']"
    )
    rpm_limit: int | None = Field(None, ge=1, description="Requests per minute limit")
    token_budget: int | None = Field(None, ge=100, description="Max tokens per dispatch")
    max_parallel: int | None = Field(None, ge=1, description="Max concurrent dispatches for this role")
    cooldown_seconds: int | None = Field(None, ge=0, description="Per-role cooldown in seconds")
    enabled: bool | None = Field(None, description="Disable a role entirely (byoai fallback)")


class PolicyResponse(BaseModel):
    agent_role: str
    preferred_execution_mode: str
    fallback_chain: list[str]
    rpm_limit: int
    token_budget: int
    max_parallel: int
    cooldown_seconds: int
    enabled: bool
    source: str  # "db" | "default"
    active_dispatches: int | None = None
    at_limit: bool | None = None


class PolicyListResponse(BaseModel):
    policies: list[PolicyResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_execution_mode(mode: str) -> bool:
    return mode in {"local", "ide", "github_actions", "byoai"}


def _valid_fallback_chain(chain: list[str]) -> bool:
    return all(_valid_execution_mode(m) for m in chain) and len(chain) > 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PolicyListResponse)
async def list_policies(
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> PolicyListResponse:
    """List all known roles with their effective policy and current dispatch activity."""
    from app.services.dispatch_policy import get_all_policies_with_status

    rows = await get_all_policies_with_status(db)
    return PolicyListResponse(policies=[PolicyResponse(**row) for row in rows])


@router.get("/status", response_model=PolicyListResponse)
async def get_policies_status(
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> PolicyListResponse:
    """Real-time status: which roles are active, at capacity, or disabled."""
    from app.services.dispatch_policy import (
        count_active_dispatches,
        get_all_policies_with_status,
    )

    rows = await get_all_policies_with_status(db)
    # Enrich with last skip reason for human-readable operator view
    return PolicyListResponse(policies=[PolicyResponse(**row) for row in rows])


@router.get("/{agent_role}", response_model=PolicyResponse)
async def get_policy(
    agent_role: str,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> PolicyResponse:
    """Get effective policy for a single agent role."""
    from app.services.dispatch_policy import count_active_dispatches, get_effective_policy

    policy = await get_effective_policy(agent_role, db)
    active = await count_active_dispatches(agent_role, db)
    return PolicyResponse(
        **policy.as_dict(),
        active_dispatches=active,
        at_limit=active >= policy.max_parallel,
    )


@router.put("/{agent_role}", response_model=PolicyResponse)
async def upsert_policy(
    agent_role: str,
    body: PolicyUpsertRequest,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
) -> PolicyResponse:
    """Create or update dispatch policy for a role.

    Only provided fields are updated; others keep their current/default values.
    """
    from app.services.dispatch_policy import count_active_dispatches, upsert_policy

    updates = body.model_dump(exclude_none=True)

    if "preferred_execution_mode" in updates and not _valid_execution_mode(
        updates["preferred_execution_mode"]
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid execution_mode '{updates['preferred_execution_mode']}'. "
            "Allowed: local, ide, github_actions, byoai",
        )
    if "fallback_chain" in updates and not _valid_fallback_chain(updates["fallback_chain"]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="fallback_chain must be a non-empty list of valid execution modes",
        )

    policy = await upsert_policy(agent_role, updates, db)
    await db.commit()
    active = await count_active_dispatches(agent_role, db)
    return PolicyResponse(
        **policy.as_dict(),
        active_dispatches=active,
        at_limit=active >= policy.max_parallel,
    )


@router.delete("/{agent_role}", status_code=status.HTTP_204_NO_CONTENT)
async def reset_policy(
    agent_role: str,
    db: AsyncSession = Depends(get_db),
    _: Any = Depends(get_current_user),
):
    """Reset dispatch policy for a role to built-in safe defaults (removes DB override)."""
    from app.services.dispatch_policy import delete_policy

    await delete_policy(agent_role, db)
    await db.commit()
