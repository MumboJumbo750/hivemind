"""Guard and TaskGuard models — TASK-3-010."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Guard(Base):
    __tablename__ = "guards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id")
    )
    skill_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="executable"
    )
    command: Mapped[Optional[str]] = mapped_column(Text)
    condition: Mapped[Optional[str]] = mapped_column(Text)
    scope: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}"
    )
    lifecycle: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="draft"
    )
    skippable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task_guards: Mapped[list["TaskGuard"]] = relationship(back_populates="guard")


class TaskGuard(Base):
    __tablename__ = "task_guards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False
    )
    guard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guards.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    result: Mapped[Optional[str]] = mapped_column(Text)
    checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    checked_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )

    guard: Mapped["Guard"] = relationship(back_populates="task_guards")
