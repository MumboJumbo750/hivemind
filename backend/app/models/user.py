import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text)
    email: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    api_key_hash: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, server_default="developer")
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    avatar_frame: Mapped[Optional[str]] = mapped_column(Text)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    preferred_theme: Mapped[str] = mapped_column(Text, server_default="space-neon")
    preferred_tone: Mapped[str] = mapped_column(Text, server_default="game")
    notification_preferences: Mapped[Optional[dict]] = mapped_column(JSONB, server_default="{}")
    exp_points: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "preferred_theme IN ('space-neon', 'industrial-amber', 'operator-mono')",
            name="valid_preferred_theme",
        ),
        CheckConstraint(
            "preferred_tone IN ('game', 'pro')",
            name="valid_preferred_tone",
        ),
    )
