"""Pydantic schemas for Governance — Phase 8."""
from typing import Literal

from pydantic import BaseModel

GovernanceLevel = Literal["manual", "assisted", "auto"]


class GovernanceConfig(BaseModel):
    review: GovernanceLevel = "manual"
    epic_proposal: GovernanceLevel = "manual"
    epic_scoping: GovernanceLevel = "manual"
    skill_merge: GovernanceLevel = "manual"
    guard_merge: GovernanceLevel = "manual"
    decision_request: GovernanceLevel = "manual"
    escalation: GovernanceLevel = "manual"
