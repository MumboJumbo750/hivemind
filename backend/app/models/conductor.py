"""Conductor Dispatch model — Phase 8 (TASK-8-004)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ConductorDispatch(Base):
    __tablename__ = "conductor_dispatches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_id: Mapped[str] = mapped_column(String(200), nullable=False)
    trigger_detail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    agent_role: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="local")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="dispatched")
    cooldown_key: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
