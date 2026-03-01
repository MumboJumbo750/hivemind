"""Epic Proposal Service — TASK-4-004.

Business logic for the Epic-Proposal workflow:
  proposed → accepted (creates Epic) | rejected (with reason).
"""
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic import Epic
from app.models.epic_proposal import EpicProposal
from app.models.user import User
from app.schemas.epic_proposal import EpicProposalCreate, EpicProposalUpdate
from app.services.event_bus import publish
from app.services.locking import check_version


class ProposalNotFoundError(Exception):
    pass


class ProposalConflictError(Exception):
    pass


class EpicProposalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_proposals(
        self,
        project_id: Optional[uuid.UUID] = None,
        state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EpicProposal], int]:
        """List proposals with optional filters. Returns (proposals, total_count)."""
        q = select(EpicProposal)
        count_q = select(func.count()).select_from(EpicProposal)

        if project_id:
            q = q.where(EpicProposal.project_id == project_id)
            count_q = count_q.where(EpicProposal.project_id == project_id)
        if state:
            q = q.where(EpicProposal.state == state)
            count_q = count_q.where(EpicProposal.state == state)

        count_result = await self.db.execute(count_q)
        total = count_result.scalar_one()

        q = q.order_by(EpicProposal.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(q)
        return list(result.scalars().all()), total

    async def get_by_id(self, proposal_id: uuid.UUID) -> EpicProposal:
        result = await self.db.execute(
            select(EpicProposal).where(EpicProposal.id == proposal_id)
        )
        proposal = result.scalar_one_or_none()
        if proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Epic Proposal '{proposal_id}' nicht gefunden.",
            )
        return proposal

    async def create(
        self,
        data: EpicProposalCreate,
        proposed_by: uuid.UUID,
    ) -> EpicProposal:
        proposal = EpicProposal(
            project_id=data.project_id,
            proposed_by=proposed_by,
            title=data.title,
            description=data.description,
            rationale=data.rationale,
            depends_on=data.depends_on,
            state="proposed",
        )
        self.db.add(proposal)
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def update(
        self,
        proposal_id: uuid.UUID,
        data: EpicProposalUpdate,
        actor_id: uuid.UUID,
        actor_role: str,
    ) -> EpicProposal:
        proposal = await self.get_by_id(proposal_id)

        if proposal.state != "proposed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nur Proposals im Status 'proposed' können bearbeitet werden.",
            )

        # RBAC: proposer or admin
        if actor_role != "admin" and proposal.proposed_by != actor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nur der Proposer oder ein Admin kann dieses Proposal bearbeiten.",
            )

        if data.expected_version is not None:
            check_version(proposal, data.expected_version)

        if data.title is not None:
            proposal.title = data.title
        if data.description is not None:
            proposal.description = data.description
        if data.rationale is not None:
            proposal.rationale = data.rationale
        if data.depends_on is not None:
            proposal.depends_on = data.depends_on

        proposal.version += 1
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def accept(
        self,
        proposal_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> EpicProposal:
        """Accept a proposal: creates an Epic with state='incoming'."""
        proposal = await self.get_by_id(proposal_id)

        if proposal.state != "proposed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Nur Proposals im Status 'proposed' können akzeptiert werden (aktuell: '{proposal.state}').",
            )

        # Create the Epic from the proposal
        from sqlalchemy import text
        result = await self.db.execute(text("SELECT nextval('epic_key_seq')"))
        seq_val = result.scalar_one()
        epic_key = f"EPIC-{seq_val}"

        epic = Epic(
            epic_key=epic_key,
            project_id=proposal.project_id,
            title=proposal.title,
            description=proposal.description,
            owner_id=proposal.proposed_by,
            state="incoming",
            priority="medium",
        )
        self.db.add(epic)
        await self.db.flush()
        await self.db.refresh(epic)

        # Update proposal
        proposal.state = "accepted"
        proposal.resulting_epic_id = epic.id
        proposal.version += 1
        await self.db.flush()
        await self.db.refresh(proposal)

        # Notification to proposer
        publish(
            "notification_created",
            {
                "type": "ProposalAccepted",
                "proposal_id": str(proposal.id),
                "epic_key": epic.epic_key,
                "proposed_by": str(proposal.proposed_by),
                "message": f"Epic Proposal akzeptiert — {epic.epic_key} erstellt",
            },
            channel="notifications",
        )

        return proposal

    async def reject(
        self,
        proposal_id: uuid.UUID,
        reason: str,
        actor_id: uuid.UUID,
    ) -> EpicProposal:
        """Reject a proposal with a reason, warn dependents."""
        proposal = await self.get_by_id(proposal_id)

        if proposal.state != "proposed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Nur Proposals im Status 'proposed' können abgelehnt werden (aktuell: '{proposal.state}').",
            )

        proposal.state = "rejected"
        proposal.rejection_reason = reason
        proposal.version += 1
        await self.db.flush()
        await self.db.refresh(proposal)

        # Notification to proposer
        publish(
            "notification_created",
            {
                "type": "ProposalRejected",
                "proposal_id": str(proposal.id),
                "proposed_by": str(proposal.proposed_by),
                "reason": reason,
                "message": f"Epic Proposal abgelehnt: {reason}",
            },
            channel="notifications",
        )

        # Warn dependent proposals
        await self._warn_dependents(proposal)

        return proposal

    async def _warn_dependents(self, rejected_proposal: EpicProposal) -> None:
        """Warn proposals that depend on the rejected proposal."""
        result = await self.db.execute(
            select(EpicProposal).where(
                EpicProposal.state == "proposed",
                EpicProposal.depends_on.any(rejected_proposal.id),
            )
        )
        dependents = result.scalars().all()

        for dep in dependents:
            publish(
                "notification_created",
                {
                    "type": "ProposalDependencyRejected",
                    "proposal_id": str(dep.id),
                    "rejected_dependency_id": str(rejected_proposal.id),
                    "rejected_dependency_title": rejected_proposal.title,
                    "proposed_by": str(dep.proposed_by),
                    "message": f"Abhängigkeit abgelehnt: '{rejected_proposal.title}'",
                },
                channel="notifications",
            )

    async def resolve_usernames(self, proposals: list[EpicProposal]) -> dict[uuid.UUID, str]:
        """Resolve proposed_by UUIDs to usernames."""
        user_ids = {p.proposed_by for p in proposals}
        if not user_ids:
            return {}
        result = await self.db.execute(
            select(User.id, User.username).where(User.id.in_(user_ids))
        )
        return {row[0]: row[1] for row in result.all()}
