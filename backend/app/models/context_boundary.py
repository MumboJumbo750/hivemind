"""ContextBoundary and TaskSkill models — Phase 4 (TASK-4-002/004)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ContextBoundary(Base):
    __tablename__ = "context_boundaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, unique=True
    )
    allowed_skills: Mapped[Optional[list[uuid.UUID]]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    allowed_docs: Mapped[Optional[list[uuid.UUID]]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    external_access: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    max_token_budget: Mapped[Optional[int]] = mapped_column(Integer, server_default="8000")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    set_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TaskSkill(Base):
    __tablename__ = "task_skills"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), primary_key=True
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True
    )
    pinned_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skill_versions.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
