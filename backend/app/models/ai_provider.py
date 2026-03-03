"""AI Provider Config model — Phase 8 (TASK-8-001)."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AIProviderConfig(Base):
    __tablename__ = "ai_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_role: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    endpoints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pool_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="round_robin")
    # Inline key (legacy / override)
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_key_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    # Reference to shared credential (preferred)
    credential_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_credentials.id", ondelete="SET NULL"),
        nullable=True,
    )
    credential = relationship("AICredential", lazy="joined")
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_budget_daily: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
