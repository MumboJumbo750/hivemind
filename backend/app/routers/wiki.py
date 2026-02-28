"""REST CRUD for Wiki Articles — TASK-3-010.

Endpoints:
  POST   /api/wiki/articles   — Create wiki article (kartograph + admin)
  PATCH  /api/wiki/articles/{id} — Update wiki article (kartograph + admin)
"""
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.wiki import WikiArticle, WikiVersion
from app.routers.deps import CurrentActor, require_role
from app.schemas.crud import WikiArticleCreate, WikiArticleResponse, WikiArticleUpdate
from app.services.audit import write_audit

router = APIRouter(prefix="/wiki/articles", tags=["wiki"])


@router.post("/", response_model=WikiArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_wiki_article(
    body: WikiArticleCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("kartograph", "admin")),
):
    """Create a new wiki article."""
    # Check slug uniqueness
    existing = await db.execute(select(WikiArticle).where(WikiArticle.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{body.slug}' existiert bereits")

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
    db.add(article)
    await db.flush()

    # Create initial version
    version = WikiVersion(
        article_id=article.id,
        version=1,
        content=body.content,
        changed_by=actor.id,
    )
    db.add(version)
    await db.flush()
    await db.refresh(article)

    await write_audit(
        tool_name="create_wiki_article",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(article.id),
    )

    return article  # type: ignore[return-value]


@router.patch("/{article_id}", response_model=WikiArticleResponse)
async def update_wiki_article(
    article_id: uuid.UUID,
    body: WikiArticleUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("kartograph", "admin")),
):
    """Update an existing wiki article with optimistic locking."""
    result = await db.execute(select(WikiArticle).where(WikiArticle.id == article_id))
    article = result.scalar_one_or_none()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Wiki-Artikel nicht gefunden")

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

    # Create new version entry
    version = WikiVersion(
        article_id=article.id,
        version=article.version,
        content=article.content,
        changed_by=actor.id,
    )
    db.add(version)
    await db.flush()
    await db.refresh(article)

    await write_audit(
        tool_name="update_wiki_article",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(article.id),
    )

    return article  # type: ignore[return-value]
