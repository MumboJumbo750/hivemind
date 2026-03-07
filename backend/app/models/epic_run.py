import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EpicRun(Base):
    __tablename__ = "epic_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    epic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("epics.id", ondelete="CASCADE"), nullable=False
    )
    started_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    analysis: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
