"""EpicProposal model — Phase 4 (TASK-4-004).

Maps to the epic_proposals table (which may have extra legacy columns).
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class EpicProposal(Base):
    __tablename__ = "epic_proposals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    proposed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")
    depends_on: Mapped[Optional[list[uuid.UUID]]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    resulting_epic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("epics.id")
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    # Legacy columns from previous schema — kept for compatibility
    suggested_priority: Mapped[Optional[str]] = mapped_column(Text)
    suggested_phase: Mapped[Optional[int]] = mapped_column(Integer)
    suggested_owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    review_reason: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Optional["Project"]] = relationship(  # type: ignore[name-defined]
        foreign_keys=[project_id]
    )
    proposer: Mapped[Optional["User"]] = relationship(  # type: ignore[name-defined]
        foreign_keys=[proposed_by]
    )
    resulting_epic: Mapped[Optional["Epic"]] = relationship()  # type: ignore[name-defined]
