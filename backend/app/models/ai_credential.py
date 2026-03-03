"""AI Credential model — zentrale Verwaltung von API-Keys.

Ein Credential kann von mehreren AIProviderConfig-Einträgen referenziert werden.
So muss z.B. ein GitHub-Copilot-Token nur einmal angelegt und kann allen Rollen zugewiesen werden.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AICredential(Base):
    __tablename__ = "ai_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g. "anthropic", "openai", "github_copilot", "github_models", "ollama", "custom"
    api_key_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    api_key_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
