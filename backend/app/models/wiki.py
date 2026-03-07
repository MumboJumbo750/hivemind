"""WikiCategory, WikiArticle and WikiVersion models."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WikiCategory(Base):
    __tablename__ = "wiki_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_categories.id")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    articles: Mapped[list["WikiArticle"]] = relationship(back_populates="category")
    children: Mapped[list["WikiCategory"]] = relationship(back_populates="parent_cat")
    parent_cat: Mapped[Optional["WikiCategory"]] = relationship(
        back_populates="children", remote_side=[id]
    )


class WikiArticle(Base):
    __tablename__ = "wiki_articles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    wiki_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True, unique=True)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_categories.id")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default="{}"
    )
    linked_epics: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default="{}"
    )
    linked_skills: Mapped[Optional[list[uuid.UUID]]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), server_default="{}"
    )
    author_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    # embedding column omitted from ORM (managed by raw SQL, pgvector type)
    embedding_model: Mapped[Optional[str]] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    origin_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nodes.id")
    )
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

    category: Mapped[Optional["WikiCategory"]] = relationship(back_populates="articles")
    versions: Mapped[list["WikiVersion"]] = relationship(back_populates="article")


class WikiVersion(Base):
    __tablename__ = "wiki_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wiki_articles.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("article_id", "version", name="uq_wiki_article_version"),
    )

    article: Mapped["WikiArticle"] = relationship(back_populates="versions")
