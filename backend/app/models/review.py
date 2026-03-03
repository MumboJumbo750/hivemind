"""Review Recommendation model — Phase 8 (TASK-8-007)."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ReviewRecommendation(Base):
    __tablename__ = "review_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_dispatch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conductor_dispatches.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)  # approve | reject | needs_human_review
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    checklist: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grace_period_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    vetoed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    vetoed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
