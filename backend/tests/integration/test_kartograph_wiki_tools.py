from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.db import AsyncSessionLocal
from app.mcp.tools.kartograph_write_tools import (
    _handle_create_wiki_article,
    _handle_update_wiki_article,
)
from app.models.wiki import WikiArticle, WikiVersion


async def _cleanup_article(article_id: uuid.UUID | None) -> None:
    if article_id is None:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WikiVersion).where(WikiVersion.article_id == article_id))
        await db.execute(delete(WikiArticle).where(WikiArticle.id == article_id))
        await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_create_wiki_article_enqueues_embedding() -> None:
    article_id: uuid.UUID | None = None
    enqueue = AsyncMock()

    try:
        with patch(
            "app.services.embedding_service.get_embedding_service",
            return_value=SimpleNamespace(enqueue=enqueue),
        ):
            result = await _handle_create_wiki_article(
                {
                    "title": f"Wiki Create {uuid.uuid4().hex[:8]}",
                    "content": "# Heading\n\nWiki body",
                    "tags": ["test", "wiki"],
                }
            )

        payload = json.loads(result[0].text)
        article_id = uuid.UUID(payload["data"]["article_id"])

        async with AsyncSessionLocal() as db:
            article = (
                await db.execute(select(WikiArticle).where(WikiArticle.id == article_id))
            ).scalar_one()
            assert article.version == 1
            assert article.tags == ["test", "wiki"]

        enqueue.assert_awaited_once()
        assert enqueue.await_args.args[0] == "wiki_articles"
        assert enqueue.await_args.args[1] == str(article_id)
        assert "Wiki body" in enqueue.await_args.args[2]
    finally:
        await _cleanup_article(article_id)


@pytest.mark.asyncio(loop_scope="session")
async def test_update_wiki_article_enqueues_embedding() -> None:
    article_id: uuid.UUID | None = None
    enqueue = AsyncMock()

    try:
        with patch(
            "app.services.embedding_service.get_embedding_service",
            return_value=SimpleNamespace(enqueue=enqueue),
        ):
            created = await _handle_create_wiki_article(
                {
                    "title": f"Wiki Update {uuid.uuid4().hex[:8]}",
                    "content": "Initial content",
                    "tags": ["initial"],
                }
            )

        create_payload = json.loads(created[0].text)
        article_id = uuid.UUID(create_payload["data"]["article_id"])
        enqueue.reset_mock()

        with patch(
            "app.services.embedding_service.get_embedding_service",
            return_value=SimpleNamespace(enqueue=enqueue),
        ):
            updated = await _handle_update_wiki_article(
                {
                    "article_id": str(article_id),
                    "content": "Updated content",
                    "tags": ["updated"],
                    "version": 1,
                }
            )

        update_payload = json.loads(updated[0].text)
        assert update_payload["data"]["version"] == 2

        async with AsyncSessionLocal() as db:
            article = (
                await db.execute(select(WikiArticle).where(WikiArticle.id == article_id))
            ).scalar_one()
            versions = list(
                (
                    await db.execute(
                        select(WikiVersion)
                        .where(WikiVersion.article_id == article_id)
                        .order_by(WikiVersion.version.asc())
                    )
                ).scalars().all()
            )
            assert article.version == 2
            assert article.content == "Updated content"
            assert article.tags == ["updated"]
            assert [version.version for version in versions] == [1, 2]

        enqueue.assert_awaited_once()
        assert enqueue.await_args.args[0] == "wiki_articles"
        assert enqueue.await_args.args[1] == str(article_id)
        assert "Updated content" in enqueue.await_args.args[2]
    finally:
        await _cleanup_article(article_id)
