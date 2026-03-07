from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.db import AsyncSessionLocal
from app.main import app
from app.models.audit import IdempotencyKey, McpInvocation
from app.models.prompt_history import PromptHistory
from app.models.skill import Skill, SkillParent, SkillVersion
from app.models.user import User
from app.models.wiki import WikiArticle, WikiVersion
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.services import skill_service, wiki_service


@asynccontextmanager
async def _actor_override(role: str = "admin") -> AsyncIterator[CurrentActor]:
    user_id = uuid.uuid4()
    username = f"knowledge-{user_id.hex[:8]}"

    async with AsyncSessionLocal() as db:
        db.add(User(id=user_id, username=username, role=role))
        await db.commit()

    actor = CurrentActor(id=user_id, username=username, role=role)

    async def _override_actor() -> CurrentActor:
        return actor

    app.dependency_overrides[get_current_actor] = _override_actor
    try:
        yield actor
    finally:
        app.dependency_overrides.pop(get_current_actor, None)
        async with AsyncSessionLocal() as db:
            await db.execute(delete(McpInvocation).where(McpInvocation.actor_id == user_id))
            await db.execute(delete(IdempotencyKey).where(IdempotencyKey.actor_id == user_id))
            await db.execute(delete(PromptHistory).where(PromptHistory.generated_by == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


async def _cleanup_skill(skill_id: uuid.UUID | None) -> None:
    if skill_id is None:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(delete(SkillParent).where(SkillParent.child_id == skill_id))
        await db.execute(delete(SkillParent).where(SkillParent.parent_id == skill_id))
        await db.execute(delete(SkillVersion).where(SkillVersion.skill_id == skill_id))
        await db.execute(delete(Skill).where(Skill.id == skill_id))
        await db.commit()


async def _cleanup_article(article_id: uuid.UUID | None) -> None:
    if article_id is None:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WikiVersion).where(WikiVersion.article_id == article_id))
        await db.execute(delete(WikiArticle).where(WikiArticle.id == article_id))
        await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_skills_rest_lifecycle_flow(client) -> None:
    skill_id: uuid.UUID | None = None
    enqueue = AsyncMock()

    async with _actor_override("admin"):
        try:
            create_payload = {
                "title": f"REST Skill {uuid.uuid4().hex[:8]}",
                "content": "Initial skill content",
                "service_scope": ["backend"],
                "stack": ["python"],
                "skill_type": "domain",
            }

            create_resp = await client.post("/api/skills", json=create_payload)
            assert create_resp.status_code == 201
            created = create_resp.json()
            skill_id = uuid.UUID(created["id"])
            assert created["lifecycle"] == "draft"
            assert created["version"] == 1
            assert created["proposed_by_username"]

            detail_resp = await client.get(f"/api/skills/{skill_id}")
            assert detail_resp.status_code == 200
            assert detail_resp.json()["id"] == str(skill_id)

            update_resp = await client.patch(
                f"/api/skills/{skill_id}",
                json={
                    "content": "Updated skill content",
                    "service_scope": ["backend", "api"],
                    "version": 1,
                },
            )
            assert update_resp.status_code == 200
            updated = update_resp.json()
            assert updated["version"] == 2
            assert updated["content"] == "Updated skill content"

            versions_resp = await client.get(f"/api/skills/{skill_id}/versions")
            assert versions_resp.status_code == 200
            versions = versions_resp.json()
            assert [version["version"] for version in versions] == [2, 1]

            submit_resp = await client.post(f"/api/skills/{skill_id}/submit")
            assert submit_resp.status_code == 200
            assert submit_resp.json()["lifecycle"] == "pending_merge"

            with patch.object(skill_service.EMBEDDING_SVC, "enqueue", enqueue):
                merge_resp = await client.post(f"/api/skills/{skill_id}/merge")
            assert merge_resp.status_code == 200
            merged = merge_resp.json()
            assert merged["lifecycle"] == "active"
            assert merged["version"] == 4
            enqueue.assert_awaited_once()

            async with AsyncSessionLocal() as db:
                skill = (await db.execute(select(Skill).where(Skill.id == skill_id))).scalar_one()
                skill_versions = list(
                    (await db.execute(select(SkillVersion).where(SkillVersion.skill_id == skill_id).order_by(SkillVersion.version.asc()))).scalars().all()
                )
                assert skill.lifecycle == "active"
                assert [version.version for version in skill_versions] == [1, 2, 4]
        finally:
            await _cleanup_skill(skill_id)


@pytest.mark.asyncio(loop_scope="session")
async def test_wiki_rest_create_and_update_flow(client) -> None:
    article_id: uuid.UUID | None = None
    enqueue = AsyncMock()

    async with _actor_override("admin"):
        try:
            create_payload = {
                "title": f"REST Wiki {uuid.uuid4().hex[:8]}",
                "slug": f"rest-wiki-{uuid.uuid4().hex[:8]}",
                "content": "# Initial\n\nWiki content",
                "tags": ["docs", "knowledge"],
            }

            with patch.object(wiki_service.EMBEDDING_SVC, "enqueue", enqueue):
                create_resp = await client.post("/api/wiki/articles/", json=create_payload)
            assert create_resp.status_code == 201
            created = create_resp.json()
            article_id = uuid.UUID(created["id"])
            assert created["version"] == 1
            assert created["slug"] == create_payload["slug"]
            enqueue.assert_awaited_once()

            enqueue.reset_mock()
            with patch.object(wiki_service.EMBEDDING_SVC, "enqueue", enqueue):
                update_resp = await client.patch(
                    f"/api/wiki/articles/{article_id}",
                    json={
                        "content": "# Updated\n\nRevised wiki content",
                        "tags": ["docs", "updated"],
                        "expected_version": 1,
                    },
                )
            assert update_resp.status_code == 200
            updated = update_resp.json()
            assert updated["version"] == 2
            assert updated["tags"] == ["docs", "updated"]

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
                assert article.content == "# Updated\n\nRevised wiki content"
                assert [version.version for version in versions] == [1, 2]

            enqueue.assert_awaited_once()
        finally:
            await _cleanup_article(article_id)
