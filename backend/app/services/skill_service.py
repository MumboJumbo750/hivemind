"""Skill Service — TASK-4-005.

Full CRUD + lifecycle transitions for the Skill Lab.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.federation import NodeIdentity
from app.models.skill import Skill, SkillParent, SkillVersion
from app.models.user import User
from app.schemas.auth import CurrentActor
from app.schemas.skill import SkillCreate, SkillReject, SkillUpdate
from app.services.embedding_service import EmbeddingPriority, get_embedding_service
from app.services.event_bus import publish
from app.services.locking import check_version

logger = logging.getLogger(__name__)
EMBEDDING_SVC = get_embedding_service()

# ── Skill Lifecycle State Machine ─────────────────────────────────────────────

SKILL_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_merge"},
    "pending_merge": {"active", "rejected"},
    "active": {"draft"},            # via propose_skill_change → new draft
    "rejected": set(),              # terminal
}


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base). Falls back to word-based estimate."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        # Fallback: rough word-based estimate
        return len(text.split())


class SkillService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── List ──────────────────────────────────────────────────────────────

    async def list_skills(
        self,
        *,
        project_id: uuid.UUID | None = None,
        lifecycle: str | None = None,
        service_scope: str | None = None,
        stack: str | None = None,
        skill_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Skill], int]:
        """Return filtered, paginated skills with total count."""
        base = select(Skill).where(Skill.deleted_at.is_(None))

        if project_id:
            base = base.where(Skill.project_id == project_id)
        if lifecycle:
            base = base.where(Skill.lifecycle == lifecycle)
        if service_scope:
            base = base.where(Skill.service_scope.any(service_scope))
        if stack:
            base = base.where(Skill.stack.any(stack))
        if skill_type:
            base = base.where(Skill.skill_type == skill_type)

        # Total count
        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # Paginated results
        query = base.order_by(Skill.title).limit(limit).offset(offset)
        result = await self.db.execute(query)
        skills = list(result.scalars().all())

        return skills, total

    # ── Get by ID ─────────────────────────────────────────────────────────

    async def get_by_id(self, skill_id: uuid.UUID) -> Skill | None:
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    # ── Get Versions ──────────────────────────────────────────────────────

    async def get_versions(self, skill_id: uuid.UUID) -> list[SkillVersion]:
        result = await self.db.execute(
            select(SkillVersion)
            .where(SkillVersion.skill_id == skill_id)
            .order_by(SkillVersion.version.desc())
        )
        return list(result.scalars().all())

    # ── Create ────────────────────────────────────────────────────────────

    async def create(self, data: SkillCreate, actor: CurrentActor) -> Skill:
        """Create a new skill in draft state with auto token count."""
        token_count = _count_tokens(data.content)

        skill = Skill(
            project_id=data.project_id,
            title=data.title,
            content=data.content,
            service_scope=data.service_scope,
            stack=data.stack,
            version_range=data.version_range,
            skill_type=data.skill_type,
            lifecycle="draft",
            owner_id=actor.id,
            proposed_by=actor.id,
            token_count=token_count,
            version=1,
        )
        self.db.add(skill)
        await self.db.flush()
        await self.db.refresh(skill)

        # Create initial version entry
        sv = SkillVersion(
            skill_id=skill.id,
            version=1,
            content=data.content,
            token_count=token_count,
            changed_by=actor.id,
        )
        self.db.add(sv)
        await self.db.flush()

        return skill

    # ── Update (draft only) ───────────────────────────────────────────────

    async def update(
        self, skill_id: uuid.UUID, data: SkillUpdate, actor: CurrentActor
    ) -> Skill:
        """Update a draft skill. Enforces ownership (or admin) + optimistic locking."""
        skill = await self.get_by_id(skill_id)
        if not skill:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden")

        if skill.lifecycle != "draft":
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nur draft-Skills können bearbeitet werden",
            )

        # Ownership check (admin can edit all)
        if actor.role != "admin" and skill.owner_id != actor.id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nur der Ersteller oder Admin darf diesen Skill bearbeiten",
            )

        check_version(skill, data.version)

        content_changed = False
        if data.title is not None:
            skill.title = data.title
        if data.content is not None:
            skill.content = data.content
            skill.token_count = _count_tokens(data.content)
            content_changed = True
        if data.service_scope is not None:
            skill.service_scope = data.service_scope
        if data.stack is not None:
            skill.stack = data.stack
        if data.version_range is not None:
            skill.version_range = data.version_range

        skill.version += 1
        await self.db.flush()

        # Create version entry on content change
        if content_changed:
            sv = SkillVersion(
                skill_id=skill.id,
                version=skill.version,
                content=skill.content,
                token_count=skill.token_count,
                changed_by=actor.id,
            )
            self.db.add(sv)
            await self.db.flush()

        await self.db.refresh(skill)
        return skill

    # ── Submit (draft → pending_merge) ────────────────────────────────────

    async def submit(self, skill_id: uuid.UUID, actor: CurrentActor) -> Skill:
        """Submit a draft skill for review (draft → pending_merge)."""
        skill = await self.get_by_id(skill_id)
        if not skill:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden")

        self._enforce_transition(skill, "pending_merge")

        # Ownership: only owner or admin can submit
        if actor.role != "admin" and skill.owner_id != actor.id:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nur der Ersteller oder Admin darf diesen Skill einreichen",
            )

        skill.lifecycle = "pending_merge"
        skill.version += 1
        await self.db.flush()
        await self.db.refresh(skill)
        await self._trigger_conductor_skill_proposal(skill)
        return skill

    # ── Merge (pending_merge → active) ────────────────────────────────────

    async def merge(self, skill_id: uuid.UUID, actor: CurrentActor) -> Skill:
        """Merge a pending skill (pending_merge → active). Admin only."""
        skill = await self.get_by_id(skill_id)
        if not skill:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden")

        self._enforce_transition(skill, "active")

        skill.lifecycle = "active"
        skill.version += 1
        await self.db.flush()

        # Create merge version entry
        sv = SkillVersion(
            skill_id=skill.id,
            version=skill.version,
            content=skill.content,
            token_count=skill.token_count,
            changed_by=actor.id,
        )
        self.db.add(sv)
        await self.db.flush()
        await self.db.refresh(skill)
        await EMBEDDING_SVC.enqueue(
            "skills",
            str(skill.id),
            _build_skill_embedding_text(skill),
            priority=EmbeddingPriority.ON_WRITE,
        )

        # Notify proposer
        if skill.proposed_by:
            asyncio.create_task(self._notify_proposer(
                skill, "SkillMergedEvent",
                f"Dein Skill '{skill.title}' wurde gemergt ✓",
            ))

        return skill

    # ── Reject (pending_merge → rejected) ─────────────────────────────────

    async def reject(
        self, skill_id: uuid.UUID, data: SkillReject, actor: CurrentActor
    ) -> Skill:
        """Reject a pending skill (pending_merge → rejected). Admin only."""
        skill = await self.get_by_id(skill_id)
        if not skill:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden")

        self._enforce_transition(skill, "rejected")

        skill.lifecycle = "rejected"
        skill.rejection_rationale = data.rationale
        skill.version += 1
        await self.db.flush()
        await self.db.refresh(skill)

        # Notify proposer
        if skill.proposed_by:
            asyncio.create_task(self._notify_proposer(
                skill, "SkillRejectedEvent",
                f"Dein Skill-Proposal '{skill.title}' wurde abgelehnt: {data.rationale}",
            ))

        return skill

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _enforce_transition(skill: Skill, target: str) -> None:
        allowed = SKILL_TRANSITIONS.get(skill.lifecycle, set())
        if target not in allowed:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "INVALID_STATE_TRANSITION",
                    "current": skill.lifecycle,
                    "target": target,
                    "allowed": sorted(allowed),
                },
            )

    async def _notify_proposer(
        self, skill: Skill, event_type: str, message: str
    ) -> None:
        """Publish notification event for the skill proposer."""
        try:
            publish(
                event_type=event_type,
                data={
                    "skill_id": str(skill.id),
                    "title": skill.title,
                    "message": message,
                    "user_id": str(skill.proposed_by),
                },
                channel="notifications",
            )
        except Exception:
            logger.exception("Failed to publish %s notification", event_type)

    async def _trigger_conductor_skill_proposal(self, skill: Skill) -> None:
        try:
            from app.services.conductor import conductor

            await conductor.on_skill_proposal(str(skill.id), self.db)
        except Exception:
            logger.exception("Conductor hook failed for skill proposal %s", skill.id)

    async def resolve_usernames(self, skills: list[Skill]) -> dict[uuid.UUID, str]:
        """Resolve user UUIDs → usernames for owner_id / proposed_by."""
        ids: set[uuid.UUID] = set()
        for s in skills:
            if s.owner_id:
                ids.add(s.owner_id)
            if s.proposed_by:
                ids.add(s.proposed_by)
        if not ids:
            return {}
        result = await self.db.execute(select(User).where(User.id.in_(ids)))
        return {u.id: u.username for u in result.scalars().all()}

    async def resolve_version_usernames(self, versions: list[SkillVersion]) -> dict[uuid.UUID, str]:
        """Resolve user UUIDs → usernames for SkillVersion.changed_by."""
        ids: set[uuid.UUID] = {v.changed_by for v in versions if v.changed_by}
        if not ids:
            return {}
        result = await self.db.execute(select(User).where(User.id.in_(ids)))
        return {u.id: u.username for u in result.scalars().all()}

    async def fork(self, skill_id: uuid.UUID) -> Skill:
        """Fork a federated skill as a local draft (TASK-F-007 logic)."""
        from fastapi import HTTPException, status

        source = await self.get_by_id(skill_id)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden.")

        if source.federation_scope != "federated":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nur federierte Skills können geforkt werden.",
            )

        existing_fork = await self.db.execute(
            select(SkillParent).where(SkillParent.parent_id == skill_id)
        )
        if existing_fork.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Skill bereits als lokaler Draft vorhanden.",
            )

        identity_result = await self.db.execute(select(NodeIdentity))
        identity = identity_result.scalar_one_or_none()
        own_node_id = identity.node_id if identity else None

        forked = Skill(
            title=f"{source.title} (Fork)",
            content=source.content,
            service_scope=source.service_scope,
            stack=source.stack,
            skill_type=source.skill_type,
            lifecycle="draft",
            federation_scope="local",
            origin_node_id=own_node_id,
            version=1,
        )
        self.db.add(forked)
        await self.db.flush()

        parent_link = SkillParent(child_id=forked.id, parent_id=source.id)
        self.db.add(parent_link)
        await self.db.flush()
        await self.db.refresh(forked)
        return forked


def _build_skill_embedding_text(skill: Skill) -> str:
    parts = [skill.title.strip(), skill.content.strip()]
    if skill.service_scope:
        parts.append("service_scope: " + ", ".join(skill.service_scope))
    if skill.stack:
        parts.append("stack: " + ", ".join(skill.stack))
    return "\n\n".join(part for part in parts if part).strip()
