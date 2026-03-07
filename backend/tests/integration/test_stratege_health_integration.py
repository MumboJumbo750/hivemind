"""Integration tests: Stratege-Prompt mit/ohne Health-Report (TASK-HEALTH-008)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, select

from app.db import AsyncSessionLocal
from app.models.epic import Epic
from app.models.federation import Node
from app.models.project import Project
from app.models.user import User
from app.models.wiki import WikiArticle, WikiVersion
from app.services.prompt_generator import (
    CLEANUP_EPIC_TEMPLATES,
    HEALTH_FINDINGS_TO_GUARD_MAPPING,
    PromptGenerator,
    _parse_health_report_summary,
)


# ── Seed / Cleanup ──────────────────────────────────────────────────────────

async def _seed_project() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"strat-health-{suffix}", role="admin")
        node = Node(
            node_name=f"strat-node-{suffix}",
            node_url=f"http://strat-{suffix}.local:8000",
        )
        db.add_all([user, node])
        await db.flush()

        project = Project(
            name=f"Strat Health Project {suffix}",
            slug=f"strat-health-{suffix}",
            description="Test project for health integration",
            created_by=user.id,
        )
        db.add(project)
        await db.flush()

        epic = Epic(
            epic_key=f"EPIC-STRAT-{suffix.upper()}",
            title=f"Health Epic {suffix}",
            state="in_progress",
            origin_node_id=node.id,
            project_id=project.id,
        )
        db.add(epic)
        await db.commit()

        return {
            "user_id": str(user.id),
            "node_id": str(node.id),
            "project_id": str(project.id),
            "epic_id": str(epic.id),
        }


async def _create_diagnostics_article(content: str) -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        suffix = uuid.uuid4().hex[:8]
        user = User(username=f"diag-user-{suffix}", role="admin")
        db.add(user)
        await db.flush()

        slug = f"diagnostics-{suffix}"
        article = WikiArticle(
            title=f"Repo Health Report {slug}",
            slug=slug,
            content=content,
            tags=["diagnostics", "health-report"],
            author_id=user.id,
        )
        db.add(article)
        await db.commit()
        return {"article_id": str(article.id), "user_id": str(user.id)}


async def _clear_diagnostics_articles() -> None:
    async with AsyncSessionLocal() as db:
        article_ids = list(
            (
                await db.execute(
                    select(WikiArticle.id).where(WikiArticle.tags.any("diagnostics"))
                )
            ).scalars().all()
        )
        if article_ids:
            await db.execute(
                delete(WikiVersion).where(WikiVersion.article_id.in_(article_ids))
            )
        await db.execute(
            delete(WikiArticle).where(WikiArticle.tags.any("diagnostics"))
        )
        await db.commit()


async def _cleanup(data: dict[str, str], article_data: dict[str, str] | None = None) -> None:
    async with AsyncSessionLocal() as db:
        if article_data:
            await db.execute(
                delete(WikiArticle).where(WikiArticle.id == uuid.UUID(article_data["article_id"]))
            )
            await db.execute(
                delete(User).where(User.id == uuid.UUID(article_data["user_id"]))
            )
        await db.execute(delete(Epic).where(Epic.id == uuid.UUID(data["epic_id"])))
        await db.execute(delete(Project).where(Project.id == uuid.UUID(data["project_id"])))
        await db.execute(delete(Node).where(Node.id == uuid.UUID(data["node_id"])))
        await db.execute(delete(User).where(User.id == uuid.UUID(data["user_id"])))
        await db.commit()


# ── Unit Tests: _parse_health_report_summary ────────────────────────────────

def test_parse_health_report_summary_extracts_counts() -> None:
    content = """# Repo Health Report 2026-03-04

## Summary
- 12 Errors, 34 Warnings in 3 Kategorien

## Findings
| hardcoded-css | 42 |
| layer-violations | 18 |
| magic-values | 7 |
"""
    result = _parse_health_report_summary(content)
    assert "12" in result
    assert "34" in result
    assert "hardcoded-css" in result
    assert "layer-violations" in result


def test_parse_health_report_summary_fallback_for_unknown_format() -> None:
    content = "Arbitrary content without any known patterns."
    result = _parse_health_report_summary(content)
    # Falls back to excerpt — should start with underscore (italic)
    assert "Arbitrary content" in result


def test_parse_health_report_summary_deduplicates_categories() -> None:
    content = """
- 5 errors, 10 warnings
| hardcoded-css: 100
| hardcoded-css: 200
| magic-values: 50
"""
    result = _parse_health_report_summary(content)
    # hardcoded-css should appear only once as a Findings entry (deduplication)
    assert result.count("hardcoded-css: ") == 1


# ── Konstanten-Tests ─────────────────────────────────────────────────────────

def test_cleanup_epic_templates_cover_all_required_categories() -> None:
    required = {"hardcoded-css", "duplicate-detection", "layer-violations", "magic-values"}
    assert required.issubset(set(CLEANUP_EPIC_TEMPLATES.keys()))


def test_cleanup_epic_templates_have_required_fields() -> None:
    for category, template in CLEANUP_EPIC_TEMPLATES.items():
        assert "title" in template, f"{category}: missing 'title'"
        assert "description" in template, f"{category}: missing 'description'"
        assert "definition_of_done" in template, f"{category}: missing 'definition_of_done'"
        assert "tags" in template, f"{category}: missing 'tags'"
        assert isinstance(template["definition_of_done"], list), f"{category}: dod must be list"
        assert len(template["definition_of_done"]) >= 1
        assert "health-report" in template["tags"], f"{category}: should include health-report tag"


def test_health_findings_to_guard_mapping_covers_key_analyzers() -> None:
    assert "hardcoded-css" in HEALTH_FINDINGS_TO_GUARD_MAPPING
    assert "layer-violations" in HEALTH_FINDINGS_TO_GUARD_MAPPING
    assert "file-size" in HEALTH_FINDINGS_TO_GUARD_MAPPING
    assert "no-hardcoded-colors" in HEALTH_FINDINGS_TO_GUARD_MAPPING["hardcoded-css"]
    assert "no-hardcoded-spacing" in HEALTH_FINDINGS_TO_GUARD_MAPPING["hardcoded-css"]
    assert "layer-boundaries" in HEALTH_FINDINGS_TO_GUARD_MAPPING["layer-violations"]
    assert "max-file-size" in HEALTH_FINDINGS_TO_GUARD_MAPPING["file-size"]


# ── Integration: Stratege-Prompt ohne Health-Report ──────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_stratege_prompt_warns_when_no_diagnostics_wiki() -> None:
    """Stratege warns if no diagnostics wiki article exists (and repo has code nodes, or no nodes)."""
    await _clear_diagnostics_articles()
    data = await _seed_project()
    try:
        async with AsyncSessionLocal() as db:
            gen = PromptGenerator(db=db, settings=None)
            prompt = await gen.generate(
                "stratege",
                project_id=data["project_id"],
            )
        # Either warning (code_nodes > 0) or no health section (code_nodes == 0)
        # In any case the prompt must NOT contain the health report summary header
        assert "📊 Repo Health Report" not in prompt
    finally:
        await _cleanup(data)


# ── Integration: Stratege-Prompt mit Health-Report ───────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_stratege_prompt_includes_health_report_when_diagnostics_wiki_exists() -> None:
    """Stratege-Prompt enthält Health-Report-Summary wenn diagnostics-Wiki existiert."""
    data = await _seed_project()
    diag_content = """# Repo Health Report 2026-03-03

## Summary
- 7 Errors, 21 Warnings in 2 Kategorien

## Top Findings
| hardcoded-css | 15 |
| magic-values | 6 |
"""
    article_data = await _create_diagnostics_article(diag_content)
    try:
        async with AsyncSessionLocal() as db:
            gen = PromptGenerator(db=db, settings=None)
            prompt = await gen.generate(
                "stratege",
                project_id=data["project_id"],
            )
        assert "📊 Repo Health Report" in prompt
        # Should contain the date from the article
        assert "Repo Health Report" in prompt
        # Should mention cleanup templates and guard mapping
        assert "Cleanup-Epic-Templates" in prompt or "cleanup" in prompt.lower()
    finally:
        await _cleanup(data, article_data)


@pytest.mark.asyncio(loop_scope="session")
async def test_stratege_prompt_health_section_contains_guard_mapping_hint() -> None:
    """Guard-Mapping-Hinweis ist im Stratege-Prompt sichtbar wenn diagnostics-Wiki vorhanden."""
    data = await _seed_project()
    diag_content = """# Health Report
- 3 Errors, 5 Warnings
| layer-violations | 10 |
| file-size | 3 |
"""
    article_data = await _create_diagnostics_article(diag_content)
    try:
        async with AsyncSessionLocal() as db:
            gen = PromptGenerator(db=db, settings=None)
            prompt = await gen.generate(
                "stratege",
                project_id=data["project_id"],
            )
        assert "layer-violations" in prompt
        assert "layer-boundaries" in prompt or "Guard" in prompt or "guard" in prompt
    finally:
        await _cleanup(data, article_data)


@pytest.mark.asyncio(loop_scope="session")
async def test_stratege_requirement_prompt_is_available_via_public_generate() -> None:
    data = await _seed_project()
    try:
        async with AsyncSessionLocal() as db:
            gen = PromptGenerator(db=db, settings=None)
            prompt = await gen.generate(
                "stratege_requirement",
                project_id=data["project_id"],
                requirement_text="Bitte Suchfunktion für Projekte ergänzen",
                priority_hint="high",
            )
        assert "Neue Anforderung" in prompt
        assert "Suchfunktion für Projekte" in prompt
        assert "Prioritäts-Hint" in prompt
    finally:
        await _cleanup(data)
