"""Skills Router — TASK-4-005.

Full REST endpoints for Skill Lab: CRUD + lifecycle transitions.
Preserves the existing fork endpoint from TASK-F-007.
"""
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor, require_role
from app.schemas.auth import CurrentActor
from app.schemas.federation import FederatedSkillResponse
from app.schemas.skill import (
    SkillCreate,
    SkillListResponse,
    SkillReject,
    SkillResponse,
    SkillUpdate,
    SkillVersionResponse,
)
from app.services.audit import write_audit
from app.services.skill_service import SkillService

router = APIRouter(prefix="/skills", tags=["skills"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _skill_to_response(
    skill, username_map: dict[uuid.UUID, str] | None = None
) -> SkillResponse:
    umap = username_map or {}
    return SkillResponse(
        id=skill.id,
        project_id=skill.project_id,
        title=skill.title,
        content=skill.content,
        service_scope=skill.service_scope or [],
        stack=skill.stack or [],
        version_range=skill.version_range,
        owner_id=skill.owner_id,
        proposed_by=skill.proposed_by,
        proposed_by_username=umap.get(skill.proposed_by) if skill.proposed_by else None,
        confidence=skill.confidence,
        skill_type=skill.skill_type,
        lifecycle=skill.lifecycle,
        version=skill.version,
        token_count=skill.token_count,
        rejection_rationale=skill.rejection_rationale,
        federation_scope=skill.federation_scope,
        origin_node_id=skill.origin_node_id,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )


# ── List Skills ───────────────────────────────────────────────────────────────

@router.get("", response_model=SkillListResponse)
async def list_skills(
    project_id: Optional[uuid.UUID] = Query(None),
    lifecycle: Optional[str] = Query(None, description="draft|pending_merge|active|rejected"),
    service_scope: Optional[str] = Query(None, description="Filter by service_scope element"),
    stack: Optional[str] = Query(None, description="Filter by stack element"),
    skill_type: Optional[str] = Query(None, description="system|domain"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SkillListResponse:
    svc = SkillService(db)
    skills, total = await svc.list_skills(
        project_id=project_id,
        lifecycle=lifecycle,
        service_scope=service_scope,
        stack=stack,
        skill_type=skill_type,
        limit=limit,
        offset=offset,
    )
    umap = await svc.resolve_usernames(skills)
    return SkillListResponse(
        data=[_skill_to_response(s, umap) for s in skills],
        total_count=total,
        has_more=(offset + limit) < total,
    )


# ── Get Skill ─────────────────────────────────────────────────────────────────

@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SkillResponse:
    svc = SkillService(db)
    skill = await svc.get_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden")
    umap = await svc.resolve_usernames([skill])
    return _skill_to_response(skill, umap)


# ── Get Skill Versions ───────────────────────────────────────────────────────

@router.get("/{skill_id}/versions", response_model=list[SkillVersionResponse])
async def get_skill_versions(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> list[SkillVersionResponse]:
    svc = SkillService(db)
    # Verify skill exists
    skill = await svc.get_by_id(skill_id)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill nicht gefunden")
    versions = await svc.get_versions(skill_id)
    umap = await svc.resolve_version_usernames(versions)
    return [
        SkillVersionResponse(
            id=v.id,
            skill_id=v.skill_id,
            version=v.version,
            content=v.content,
            token_count=v.token_count,
            changed_by=v.changed_by,
            changed_by_username=umap.get(v.changed_by),
            created_at=v.created_at,
        )
        for v in versions
    ]


# ── Create Skill (draft) ─────────────────────────────────────────────────────

@router.post("", response_model=SkillResponse, status_code=status.HTTP_201_CREATED)
async def create_skill(
    body: SkillCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SkillResponse:
    t0 = time.perf_counter()
    svc = SkillService(db)
    skill = await svc.create(body, actor)
    await db.commit()
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="create_skill",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"skill_id": str(skill.id), "title": skill.title},
        duration_ms=duration,
    )
    umap = await svc.resolve_usernames([skill])
    return _skill_to_response(skill, umap)


# ── Update Skill (draft only) ────────────────────────────────────────────────

@router.patch("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SkillResponse:
    t0 = time.perf_counter()
    svc = SkillService(db)
    skill = await svc.update(skill_id, body, actor)
    await db.commit()
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="update_skill",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"skill_id": str(skill_id), **body.model_dump(mode="json")},
        output_payload={"skill_id": str(skill.id), "version": skill.version},
        duration_ms=duration,
    )
    umap = await svc.resolve_usernames([skill])
    return _skill_to_response(skill, umap)


# ── Submit (draft → pending_merge) ───────────────────────────────────────────

@router.post("/{skill_id}/submit", response_model=SkillResponse)
async def submit_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> SkillResponse:
    t0 = time.perf_counter()
    svc = SkillService(db)
    skill = await svc.submit(skill_id, actor)
    await db.commit()
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="submit_skill",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"skill_id": str(skill_id)},
        output_payload={"skill_id": str(skill.id), "lifecycle": skill.lifecycle},
        duration_ms=duration,
    )
    umap = await svc.resolve_usernames([skill])
    return _skill_to_response(skill, umap)


# ── Merge (pending_merge → active) — Admin only ─────────────────────────────

@router.post("/{skill_id}/merge", response_model=SkillResponse)
async def merge_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "triage")),
) -> SkillResponse:
    t0 = time.perf_counter()
    svc = SkillService(db)
    skill = await svc.merge(skill_id, actor)
    await db.commit()
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="merge_skill",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"skill_id": str(skill_id)},
        output_payload={"skill_id": str(skill.id), "lifecycle": skill.lifecycle},
        duration_ms=duration,
    )
    umap = await svc.resolve_usernames([skill])
    return _skill_to_response(skill, umap)


# ── Reject (pending_merge → rejected) — Admin only ──────────────────────────

@router.post("/{skill_id}/reject", response_model=SkillResponse)
async def reject_skill(
    skill_id: uuid.UUID,
    body: SkillReject,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "triage")),
) -> SkillResponse:
    t0 = time.perf_counter()
    svc = SkillService(db)
    skill = await svc.reject(skill_id, body, actor)
    await db.commit()
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="reject_skill",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"skill_id": str(skill_id), "rationale": body.rationale},
        output_payload={"skill_id": str(skill.id), "lifecycle": skill.lifecycle},
        duration_ms=duration,
    )
    umap = await svc.resolve_usernames([skill])
    return _skill_to_response(skill, umap)


# ── Fork (federated → local draft) — Existing from TASK-F-007 ───────────────

@router.post(
    "/{skill_id}/fork",
    response_model=FederatedSkillResponse,
    status_code=status.HTTP_201_CREATED,
)
async def fork_skill(
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FederatedSkillResponse:
    """Fork a federated skill as a local draft.

    - Source skill must have federation_scope='federated'
    - Creates new local draft skill with extends link
    - Returns 409 if a fork already exists
    """
    svc = SkillService(db)
    forked = await svc.fork(skill_id)
    await db.commit()

    return FederatedSkillResponse(
        id=forked.id,
        title=forked.title,
        origin_node_id=forked.origin_node_id,
        federation_scope=forked.federation_scope,
        created=True,
    )
