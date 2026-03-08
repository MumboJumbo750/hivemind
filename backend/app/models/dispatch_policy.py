"""Agent Dispatch Policy model — TASK-AGENT-003."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AgentDispatchPolicy(Base):
    """Per-role dispatch policy persisted in DB.

    Only overrides are stored here; missing columns fall back to safe defaults
    defined in app/services/dispatch_policy.py.
    """

    __tablename__ = "agent_dispatch_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_role: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    preferred_execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    fallback_chain: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    rpm_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_budget: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_parallel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cooldown_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
