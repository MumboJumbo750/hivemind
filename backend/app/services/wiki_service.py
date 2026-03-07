"""Wiki Service — TASK-8.

CRUD logic for WikiArticle + WikiVersion, extracted from wiki.py router.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wiki import WikiArticle, WikiVersion
from app.schemas.auth import CurrentActor
from app.schemas.crud import WikiArticleCreate, WikiArticleUpdate
from app.services.embedding_service import EmbeddingPriority, get_embedding_service

EMBEDDING_SVC = get_embedding_service()


class WikiService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, article_id: uuid.UUID) -> WikiArticle | None:
        result = await self.db.execute(
            select(WikiArticle).where(WikiArticle.id == article_id)
        )
        return result.scalar_one_or_none()

    async def create(self, body: WikiArticleCreate, actor: CurrentActor) -> WikiArticle:
        """Create a new wiki article with initial version entry."""
        existing = await self.db.execute(
            select(WikiArticle).where(WikiArticle.slug == body.slug)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Slug '{body.slug}' existiert bereits",
            )

        article = WikiArticle(
            title=body.title,
            slug=body.slug,
            content=body.content,
            category_id=body.category_id,
            tags=body.tags,
            linked_epics=[str(e) for e in body.linked_epics] if body.linked_epics else [],
            linked_skills=[str(s) for s in body.linked_skills] if body.linked_skills else [],
            author_id=actor.id,
            version=1,
        )
        self.db.add(article)
        await self.db.flush()

        version = WikiVersion(
            article_id=article.id,
            version=1,
            content=body.content,
            changed_by=actor.id,
        )
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(article)
        await EMBEDDING_SVC.enqueue(
            "wiki_articles",
            str(article.id),
            _build_wiki_embedding_text(article),
            priority=EmbeddingPriority.ON_WRITE,
        )
        return article

    async def update(
        self, article_id: uuid.UUID, body: WikiArticleUpdate, actor: CurrentActor
    ) -> WikiArticle:
        """Update an existing wiki article with optimistic locking."""
        article = await self.get_by_id(article_id)
        if not article:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wiki-Artikel nicht gefunden",
            )

        if body.expected_version is not None and article.version != body.expected_version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Version-Conflict: erwartet {body.expected_version}, aktuell {article.version}",
            )

        if body.title is not None:
            article.title = body.title
        if body.content is not None:
            article.content = body.content
        if body.category_id is not None:
            article.category_id = body.category_id
        if body.tags is not None:
            article.tags = body.tags
        if body.linked_epics is not None:
            article.linked_epics = [str(e) for e in body.linked_epics]
        if body.linked_skills is not None:
            article.linked_skills = [str(s) for s in body.linked_skills]

        article.version += 1

        version = WikiVersion(
            article_id=article.id,
            version=article.version,
            content=article.content,
            changed_by=actor.id,
        )
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(article)
        await EMBEDDING_SVC.enqueue(
            "wiki_articles",
            str(article.id),
            _build_wiki_embedding_text(article),
            priority=EmbeddingPriority.ON_WRITE,
        )
        return article


def _build_wiki_embedding_text(article: WikiArticle) -> str:
    parts = [article.title.strip(), article.content.strip()]
    if article.tags:
        parts.append("tags: " + ", ".join(article.tags))
    return "\n\n".join(part for part in parts if part).strip()
