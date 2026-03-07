"""Unified key generation for all Hivemind entities.

Single source of truth for generating human-readable keys.
All keys use PostgreSQL sequences — atomic, gap-free, collision-proof.

Entity types and their formats:
    Epic:  EPIC-{n}    (sequence: epic_key_seq)
    Task:  TASK-{n}    (sequence: task_key_seq)
    Skill: SKILL-{n}   (sequence: skill_key_seq)
    Wiki:  WIKI-{n}    (sequence: wiki_key_seq)
    Guard: GUARD-{n}   (sequence: guard_key_seq)
    Doc:   DOC-{n}     (sequence: doc_key_seq)
"""
from __future__ import annotations

import re
import uuid as _uuid
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


# ── Key Generators ────────────────────────────────────────────────────────────


async def next_epic_key(db: AsyncSession) -> str:
    """Generate the next epic key using the epic_key_seq sequence."""
    result = await db.execute(text("SELECT nextval('epic_key_seq')"))
    return f"EPIC-{result.scalar_one()}"


async def next_task_key(db: AsyncSession) -> str:
    """Generate the next task key using the task_key_seq sequence."""
    result = await db.execute(text("SELECT nextval('task_key_seq')"))
    return f"TASK-{result.scalar_one()}"


async def next_skill_key(db: AsyncSession) -> str:
    """Generate the next skill key using the skill_key_seq sequence."""
    result = await db.execute(text("SELECT nextval('skill_key_seq')"))
    return f"SKILL-{result.scalar_one()}"


async def next_wiki_key(db: AsyncSession) -> str:
    """Generate the next wiki key using the wiki_key_seq sequence."""
    result = await db.execute(text("SELECT nextval('wiki_key_seq')"))
    return f"WIKI-{result.scalar_one()}"


async def next_guard_key(db: AsyncSession) -> str:
    """Generate the next guard key using the guard_key_seq sequence."""
    result = await db.execute(text("SELECT nextval('guard_key_seq')"))
    return f"GUARD-{result.scalar_one()}"


async def next_doc_key(db: AsyncSession) -> str:
    """Generate the next doc key using the doc_key_seq sequence."""
    result = await db.execute(text("SELECT nextval('doc_key_seq')"))
    return f"DOC-{result.scalar_one()}"


# ── Slugify Utility ───────────────────────────────────────────────────────────


def slugify(text_input: str) -> str:
    """Generate a URL-safe slug from a title.

    Handles German umlauts and special characters.
    This is the SINGLE canonical implementation — do not duplicate.

    Examples:
        "Architektur-Übersicht"  → "architektur-uebersicht"
        "Hello World!"           → "hello-world"
        ""                       → "untitled"
    """
    slug = text_input.lower().strip()
    slug = re.sub(r"[äÄ]", "ae", slug)
    slug = re.sub(r"[öÖ]", "oe", slug)
    slug = re.sub(r"[üÜ]", "ue", slug)
    slug = re.sub(r"[ß]", "ss", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "untitled"


# ── Identifier Resolvers ──────────────────────────────────────────────────────
# Accept either UUID or human-readable key (e.g. "SKILL-7" or "550e8400-...")
# and return the ORM model instance, or None if not found.


def _is_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        _uuid.UUID(value)
        return True
    except ValueError:
        return False


async def resolve_skill(db: AsyncSession, identifier: str) -> Optional[object]:
    """Resolve a skill by UUID or skill_key (e.g. 'SKILL-7')."""
    from app.models.skill import Skill

    if _is_uuid(identifier):
        result = await db.execute(select(Skill).where(Skill.id == _uuid.UUID(identifier)))
    else:
        result = await db.execute(select(Skill).where(Skill.skill_key == identifier))
    return result.scalar_one_or_none()


async def resolve_guard(db: AsyncSession, identifier: str) -> Optional[object]:
    """Resolve a guard by UUID or guard_key (e.g. 'GUARD-3')."""
    from app.models.guard import Guard

    if _is_uuid(identifier):
        result = await db.execute(select(Guard).where(Guard.id == _uuid.UUID(identifier)))
    else:
        result = await db.execute(select(Guard).where(Guard.guard_key == identifier))
    return result.scalar_one_or_none()


async def resolve_wiki_article(db: AsyncSession, identifier: str) -> Optional[object]:
    """Resolve a wiki article by UUID, wiki_key (e.g. 'WIKI-5'), or slug."""
    from app.models.wiki import WikiArticle

    if _is_uuid(identifier):
        result = await db.execute(
            select(WikiArticle).where(WikiArticle.id == _uuid.UUID(identifier))
        )
    elif identifier.upper().startswith("WIKI-"):
        result = await db.execute(
            select(WikiArticle).where(WikiArticle.wiki_key == identifier.upper())
        )
    else:
        # Fallback: treat as slug
        result = await db.execute(
            select(WikiArticle).where(WikiArticle.slug == identifier)
        )
    return result.scalar_one_or_none()


async def resolve_doc(db: AsyncSession, identifier: str) -> Optional[object]:
    """Resolve a doc by UUID or doc_key (e.g. 'DOC-8')."""
    from app.models.doc import Doc

    if _is_uuid(identifier):
        result = await db.execute(select(Doc).where(Doc.id == _uuid.UUID(identifier)))
    else:
        result = await db.execute(select(Doc).where(Doc.doc_key == identifier))
    return result.scalar_one_or_none()
