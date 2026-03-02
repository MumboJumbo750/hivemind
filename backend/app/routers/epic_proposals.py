"""Epic Proposals Router — TASK-4-004.

REST CRUD for the Epic-Proposal workflow + requirement-capture draft endpoint.
"""
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor, require_role
from app.schemas.auth import CurrentActor
from app.schemas.epic_proposal import (
    EpicProposalCreate,
    EpicProposalListResponse,
    EpicProposalReject,
    EpicProposalResponse,
    EpicProposalUpdate,
    RequirementDraftRequest,
    RequirementDraftResponse,
)
from app.services.audit import write_audit
from app.services.epic_proposal_service import EpicProposalService
from app.services.prompt_generator import PromptGenerator, count_tokens

router = APIRouter(prefix="/epic-proposals", tags=["epic-proposals"])


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=EpicProposalListResponse)
async def list_epic_proposals(
    project_id: Optional[uuid.UUID] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicProposalListResponse:
    svc = EpicProposalService(db)
    proposals, total = await svc.list_proposals(
        project_id=project_id, state=state, limit=limit, offset=offset
    )
    username_map = await svc.resolve_usernames(proposals)
    return EpicProposalListResponse(
        data=[
            EpicProposalResponse(
                id=p.id,
                project_id=p.project_id,
                proposed_by=p.proposed_by,
                proposed_by_username=username_map.get(p.proposed_by),
                title=p.title,
                description=p.description,
                rationale=p.rationale,
                state=p.state,
                depends_on=p.depends_on,
                resulting_epic_id=p.resulting_epic_id,
                rejection_reason=p.rejection_reason,
                version=p.version,
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in proposals
        ],
        total_count=total,
        has_more=(offset + limit) < total,
    )


# ─── Get by ID ───────────────────────────────────────────────────────────────

@router.get("/{proposal_id}", response_model=EpicProposalResponse)
async def get_epic_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicProposalResponse:
    svc = EpicProposalService(db)
    p = await svc.get_by_id(proposal_id)
    username_map = await svc.resolve_usernames([p])
    return EpicProposalResponse(
        id=p.id,
        project_id=p.project_id,
        proposed_by=p.proposed_by,
        proposed_by_username=username_map.get(p.proposed_by),
        title=p.title,
        description=p.description,
        rationale=p.rationale,
        state=p.state,
        depends_on=p.depends_on,
        resulting_epic_id=p.resulting_epic_id,
        rejection_reason=p.rejection_reason,
        version=p.version,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# ─── Create ──────────────────────────────────────────────────────────────────

@router.post("", response_model=EpicProposalResponse, status_code=status.HTTP_201_CREATED)
async def create_epic_proposal(
    body: EpicProposalCreate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicProposalResponse:
    t0 = time.perf_counter()
    svc = EpicProposalService(db)
    p = await svc.create(body, proposed_by=actor.id)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="create_epic_proposal",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"proposal_id": str(p.id)},
        duration_ms=duration,
    )
    return EpicProposalResponse.model_validate(p)


# ─── Update ──────────────────────────────────────────────────────────────────

@router.patch("/{proposal_id}", response_model=EpicProposalResponse)
async def update_epic_proposal(
    proposal_id: uuid.UUID,
    body: EpicProposalUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> EpicProposalResponse:
    t0 = time.perf_counter()
    svc = EpicProposalService(db)
    p = await svc.update(proposal_id, body, actor_id=actor.id, actor_role=actor.role)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="update_epic_proposal",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload=body.model_dump(mode="json"),
        output_payload={"proposal_id": str(p.id), "version": p.version},
        duration_ms=duration,
    )
    return EpicProposalResponse.model_validate(p)


# ─── Accept ──────────────────────────────────────────────────────────────────

@router.post("/{proposal_id}/accept", response_model=EpicProposalResponse)
async def accept_epic_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "triage")),
) -> EpicProposalResponse:
    t0 = time.perf_counter()
    svc = EpicProposalService(db)
    p = await svc.accept(proposal_id, actor_id=actor.id)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="accept_epic_proposal",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"proposal_id": str(proposal_id)},
        output_payload={
            "proposal_id": str(p.id),
            "resulting_epic_id": str(p.resulting_epic_id),
        },
        duration_ms=duration,
    )
    return EpicProposalResponse.model_validate(p)


# ─── Reject ──────────────────────────────────────────────────────────────────

@router.post("/{proposal_id}/reject", response_model=EpicProposalResponse)
async def reject_epic_proposal(
    proposal_id: uuid.UUID,
    body: EpicProposalReject,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(require_role("admin", "triage")),
) -> EpicProposalResponse:
    t0 = time.perf_counter()
    svc = EpicProposalService(db)
    p = await svc.reject(proposal_id, reason=body.reason, actor_id=actor.id)
    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="reject_epic_proposal",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"proposal_id": str(proposal_id), "reason": body.reason},
        output_payload={"proposal_id": str(p.id), "state": p.state},
        duration_ms=duration,
    )
    return EpicProposalResponse.model_validate(p)


# ─── Requirement Draft ────────────────────────────────────────────────────────

@router.post("/draft-requirement", response_model=RequirementDraftResponse, status_code=status.HTTP_200_OK)
async def draft_requirement(
    body: RequirementDraftRequest,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> RequirementDraftResponse:
    """Generate an enriched Stratege prompt from a free-text requirement.

    Creates an epic_proposals entry with state='draft' and returns the
    ready-to-use prompt together with enrichment metadata.
    """
    from app.models.epic_proposal import EpicProposal

    t0 = time.perf_counter()

    # Generate enriched Stratege prompt
    gen = PromptGenerator(db)
    try:
        prompt = await gen._stratege_requirement(
            project_id=str(body.project_id),
            requirement_text=body.text,
            priority_hint=body.priority_hint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    token_count = count_tokens(prompt)

    # Persist draft proposal so the user can later promote it to 'proposed'
    draft = EpicProposal(
        project_id=body.project_id,
        proposed_by=actor.id,
        title=body.text[:80] + ("…" if len(body.text) > 80 else ""),
        description=body.text,
        rationale=None,
        state="draft",
        raw_requirement=body.text,
    )
    db.add(draft)
    await db.flush()
    await db.commit()

    duration = int((time.perf_counter() - t0) * 1000)
    await write_audit(
        tool_name="draft_requirement",
        actor_id=actor.id,
        actor_role=actor.role,
        input_payload={"project_id": str(body.project_id), "text_len": len(body.text)},
        output_payload={"draft_id": str(draft.id), "token_count": token_count},
        duration_ms=duration,
    )

    return RequirementDraftResponse(
        prompt=prompt,
        token_count=token_count,
        draft_id=draft.id,
        enrichment={"priority_hint": body.priority_hint, "tags": body.tags or []},
    )
