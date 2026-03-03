"""Skill, SkillVersion and SkillParent models."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    service_scope: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    stack: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    version_range: Mapped[Optional[dict]] = mapped_column(JSONB)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(3, 2), server_default="0.5"
    )
    source_epics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default="{}"
    )
    skill_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="domain"
    )
    lifecycle: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="draft"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    source_slug: Mapped[Optional[str]] = mapped_column(Text, nullable=True, unique=True)
    # embedding column omitted from ORM (managed by raw SQL, pgvector type)
    embedding_model: Mapped[Optional[str]] = mapped_column(Text)
    origin_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nodes.id")
    )
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    proposed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    rejection_rationale: Mapped[Optional[str]] = mapped_column(Text)
    federation_scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="local"
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "skill_type IN ('system', 'domain', 'runtime')",
            name="chk_skill_type",
        ),
        CheckConstraint(
            "origin_node_id IS NOT NULL OR owner_id IS NOT NULL",
            name="chk_skill_origin_or_owner",
        ),
    )

    versions: Mapped[list["SkillVersion"]] = relationship(back_populates="skill")
    parent_links: Mapped[list["SkillParent"]] = relationship(
        foreign_keys="SkillParent.child_id", back_populates="child"
    )
    child_links: Mapped[list["SkillParent"]] = relationship(
        foreign_keys="SkillParent.parent_id", back_populates="parent"
    )


class SkillVersion(Base):
    __tablename__ = "skill_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_versions: Mapped[Optional[list]] = mapped_column(JSONB, server_default="[]")
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    diff_from_previous: Mapped[Optional[str]] = mapped_column(Text)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("skill_id", "version", name="uq_skill_version"),
    )

    skill: Mapped["Skill"] = relationship(back_populates="versions")


class SkillParent(Base):
    __tablename__ = "skill_parents"

    child_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True
    )
    parent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("skills.id"), primary_key=True
    )
    order_idx: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("child_id != parent_id", name="chk_skill_no_self_parent"),
    )

    child: Mapped["Skill"] = relationship(
        foreign_keys=[child_id], back_populates="parent_links"
    )
    parent: Mapped["Skill"] = relationship(
        foreign_keys=[parent_id], back_populates="child_links"
    )
