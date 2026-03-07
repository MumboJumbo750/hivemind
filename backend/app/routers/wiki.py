"""REST CRUD for Wiki Articles — TASK-3-010.

Endpoints:
  POST   /api/wiki/articles   — Create wiki article (kartograph + admin)
  PATCH  /api/wiki/articles/{id} — Update wiki article (kartograph + admin)
"""
import time
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import CurrentActor, require_role
from app.schemas.crud import WikiArticleCreate, WikiArticleResponse, WikiArticleUpdate
from app.services.audit import write_audit
from app.services.wiki_service import WikiService

router = APIRouter(prefix="/wiki/articles", tags=["wiki"])


@router.post("/", response_model=WikiArticleResponse, status_code=status.HTTP_201_CREATED)
async def create_wiki_article(
    body: WikiArticleCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("kartograph", "admin")),
):
    """Create a new wiki article."""
    svc = WikiService(db)
    article = await svc.create(body, actor)

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
    svc = WikiService(db)
    article = await svc.update(article_id, body, actor)

    await write_audit(
        tool_name="update_wiki_article",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        target_id=str(article.id),
    )

    return article  # type: ignore[return-value]
