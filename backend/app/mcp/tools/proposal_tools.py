"""MCP Epic-Proposal Write-Tools — TASK-4-001.

MCP tools for the Epic-Proposal workflow:
- hivemind/propose_epic
- hivemind/update_epic_proposal
- hivemind/accept_epic_proposal
- hivemind/reject_epic_proposal
"""
from __future__ import annotations

import json
import logging
import uuid

from mcp.types import TextContent, Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/propose_epic
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/propose_epic",
        description=(
            "Create a new epic proposal (state='proposed'). "
            "Supports optional idempotency_key to prevent duplicates."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project UUID"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "rationale": {"type": "string"},
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "UUIDs of proposals this depends on",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Optional idempotency key to prevent duplicates",
                },
            },
            "required": ["project_id", "title", "description", "rationale"],
        },
    ),
    handler=lambda args: _handle_propose_epic(args),
)


async def _handle_propose_epic(args: dict) -> list[TextContent]:
    from sqlalchemy import select

    from app.models.epic_proposal import EpicProposal

    project_id = uuid.UUID(args["project_id"])
    depends_on = [uuid.UUID(d) for d in args.get("depends_on", [])]
    idemp_key = args.get("idempotency_key")

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Idempotency check
                if idemp_key:
                    existing = await db.execute(
                        select(EpicProposal).where(
                            EpicProposal.title == args["title"],
                            EpicProposal.project_id == project_id,
                            EpicProposal.proposed_by == ADMIN_ID,
                        )
                    )
                    found = existing.scalar_one_or_none()
                    if found:
                        return _ok({
                            "data": {
                                "id": str(found.id),
                                "title": found.title,
                                "state": found.state,
                                "duplicate": True,
                            },
                            "meta": {"version": found.version},
                        })

                proposal = EpicProposal(
                    project_id=project_id,
                    proposed_by=ADMIN_ID,
                    title=args["title"],
                    description=args["description"],
                    rationale=args["rationale"],
                    depends_on=depends_on,
                    state="proposed",
                )
                db.add(proposal)
                await db.flush()
                await db.refresh(proposal)

                return _ok({
                    "data": {
                        "id": str(proposal.id),
                        "title": proposal.title,
                        "state": proposal.state,
                    },
                    "meta": {"version": proposal.version},
                })
    except Exception as exc:
        logger.exception("propose_epic failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/update_epic_proposal
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/update_epic_proposal",
        description=(
            "Update an epic proposal. Only allowed when state='proposed'. "
            "Uses optimistic locking (version field required)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "Proposal UUID"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "rationale": {"type": "string"},
                "depends_on": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "version": {"type": "integer", "description": "Expected version for optimistic locking"},
            },
            "required": ["proposal_id", "version"],
        },
    ),
    handler=lambda args: _handle_update_epic_proposal(args),
)


async def _handle_update_epic_proposal(args: dict) -> list[TextContent]:
    from app.models.epic_proposal import EpicProposal
    from app.services.locking import check_version

    proposal_id = uuid.UUID(args["proposal_id"])
    expected_version = args["version"]

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                proposal = await db.get(EpicProposal, proposal_id)
                if not proposal:
                    return _err("ENTITY_NOT_FOUND", "Proposal not found", 404)

                if proposal.state != "proposed":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Cannot update proposal in state '{proposal.state}' — only 'proposed' allowed",
                        422,
                    )

                check_version(proposal, expected_version)

                if "title" in args:
                    proposal.title = args["title"]
                if "description" in args:
                    proposal.description = args["description"]
                if "rationale" in args:
                    proposal.rationale = args["rationale"]
                if "depends_on" in args:
                    proposal.depends_on = [uuid.UUID(d) for d in args["depends_on"]]

                proposal.version += 1
                await db.flush()
                await db.refresh(proposal)

                return _ok({
                    "data": {
                        "id": str(proposal.id),
                        "title": proposal.title,
                        "state": proposal.state,
                    },
                    "meta": {"version": proposal.version},
                })
    except Exception as exc:
        if hasattr(exc, "status_code") and exc.status_code == 409:
            return _err("VERSION_CONFLICT", str(exc.detail), 409)
        logger.exception("update_epic_proposal failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/accept_epic_proposal
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/accept_epic_proposal",
        description=(
            "Accept an epic proposal. Creates a real Epic (state='incoming') "
            "and sets resulting_epic_id on the proposal."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "Proposal UUID"},
            },
            "required": ["proposal_id"],
        },
    ),
    handler=lambda args: _handle_accept_epic_proposal(args),
)


async def _handle_accept_epic_proposal(args: dict) -> list[TextContent]:
    from sqlalchemy import text

    from app.models.epic import Epic
    from app.models.epic_proposal import EpicProposal
    from app.services.event_bus import publish

    proposal_id = uuid.UUID(args["proposal_id"])

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                proposal = await db.get(EpicProposal, proposal_id)
                if not proposal:
                    return _err("ENTITY_NOT_FOUND", "Proposal not found", 404)

                if proposal.state != "proposed":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Cannot accept proposal in state '{proposal.state}'",
                        422,
                    )

                # Generate epic key
                seq = await db.execute(text("SELECT nextval('epic_key_seq')"))
                epic_key = f"EPIC-{seq.scalar_one()}"

                # Create real epic
                epic = Epic(
                    epic_key=epic_key,
                    project_id=proposal.project_id,
                    title=proposal.title,
                    description=proposal.description,
                    state="incoming",
                    owner_id=proposal.proposed_by,
                )
                db.add(epic)
                await db.flush()
                await db.refresh(epic)

                # Update proposal
                proposal.state = "accepted"
                proposal.resulting_epic_id = epic.id
                proposal.version += 1
                await db.flush()

                # Notify proposer
                publish(
                    event_type="ProposalAccepted",
                    data={
                        "proposal_id": str(proposal.id),
                        "title": proposal.title,
                        "epic_key": epic_key,
                        "user_id": str(proposal.proposed_by),
                    },
                    channel="notifications",
                )

                return _ok({
                    "data": {
                        "proposal_id": str(proposal.id),
                        "state": "accepted",
                        "resulting_epic_id": str(epic.id),
                        "epic_key": epic_key,
                    },
                    "meta": {"version": proposal.version},
                })
    except Exception as exc:
        logger.exception("accept_epic_proposal failed")
        return _err("INTERNAL_ERROR", str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# hivemind/reject_epic_proposal
# ═══════════════════════════════════════════════════════════════════════════════

register_tool(
    Tool(
        name="hivemind/reject_epic_proposal",
        description=(
            "Reject an epic proposal with a reason. Sends notification to proposer "
            "and warns dependent proposals."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string", "description": "Proposal UUID"},
                "reason": {"type": "string", "description": "Rejection reason"},
            },
            "required": ["proposal_id", "reason"],
        },
    ),
    handler=lambda args: _handle_reject_epic_proposal(args),
)


async def _handle_reject_epic_proposal(args: dict) -> list[TextContent]:
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import ARRAY

    from app.models.epic_proposal import EpicProposal
    from app.services.event_bus import publish

    proposal_id = uuid.UUID(args["proposal_id"])
    reason = args["reason"]

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                proposal = await db.get(EpicProposal, proposal_id)
                if not proposal:
                    return _err("ENTITY_NOT_FOUND", "Proposal not found", 404)

                if proposal.state != "proposed":
                    return _err(
                        "INVALID_STATE_TRANSITION",
                        f"Cannot reject proposal in state '{proposal.state}'",
                        422,
                    )

                proposal.state = "rejected"
                proposal.rejection_reason = reason
                proposal.version += 1
                await db.flush()

                # Notify proposer
                publish(
                    event_type="ProposalRejected",
                    data={
                        "proposal_id": str(proposal.id),
                        "title": proposal.title,
                        "reason": reason,
                        "user_id": str(proposal.proposed_by),
                    },
                    channel="notifications",
                )

                # Warn dependent proposals
                dependents = await db.execute(
                    select(EpicProposal).where(
                        EpicProposal.depends_on.any(proposal.id),
                        EpicProposal.state == "proposed",
                    )
                )
                warned = []
                for dep in dependents.scalars().all():
                    publish(
                        event_type="ProposalDependencyRejected",
                        data={
                            "proposal_id": str(dep.id),
                            "title": dep.title,
                            "rejected_dependency_id": str(proposal.id),
                            "rejected_dependency_title": proposal.title,
                            "user_id": str(dep.proposed_by),
                        },
                        channel="notifications",
                    )
                    warned.append(str(dep.id))

                return _ok({
                    "data": {
                        "proposal_id": str(proposal.id),
                        "state": "rejected",
                        "reason": reason,
                        "dependents_warned": warned,
                    },
                    "meta": {"version": proposal.version},
                })
    except Exception as exc:
        logger.exception("reject_epic_proposal failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
