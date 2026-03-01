"""MCP Epic Restructure Tool — TASK-5-012.

- hivemind/propose_epic_restructure — Propose split/merge/task_move of epics
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from mcp.types import TextContent, Tool
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.event_bus import publish

logger = logging.getLogger(__name__)

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
VALID_PROPOSAL_TYPES = ("split", "merge", "task_move")


def _ok(data: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, default=str))]


def _err(code: str, message: str, status: int = 400) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({
        "error": {"code": code, "message": message, "status": status}
    }))]


register_tool(
    Tool(
        name="hivemind/propose_epic_restructure",
        description=(
            "Propose an epic restructure (split, merge, or task_move). "
            "Creates a proposal record with state=proposed. "
            "Sends notification to admins."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "epic_key": {"type": "string", "description": "Target epic key"},
                "proposal_type": {
                    "type": "string",
                    "enum": ["split", "merge", "task_move"],
                    "description": "Type of restructure",
                },
                "rationale": {"type": "string", "description": "Why this restructure is needed"},
                "target_epic_key": {
                    "type": "string",
                    "description": "For merge/task_move: target epic key",
                },
                "task_keys": {
                    "type": "array", "items": {"type": "string"},
                    "description": "For task_move: task keys to move",
                },
                "split_plan": {
                    "type": "object",
                    "description": "For split: description of new epics",
                },
                "code_node_refs": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Related code node paths for context",
                },
            },
            "required": ["epic_key", "proposal_type", "rationale"],
        },
    ),
    handler=lambda args: _handle_propose_epic_restructure(args),
)


async def _handle_propose_epic_restructure(args: dict) -> list[TextContent]:
    from app.models.epic import Epic
    from app.models.decision import DecisionRequest

    epic_key = args.get("epic_key", "")
    proposal_type = args.get("proposal_type", "")
    rationale = args.get("rationale", "").strip()

    if proposal_type not in VALID_PROPOSAL_TYPES:
        return _err(
            "VALIDATION_ERROR",
            f"proposal_type muss einer von {VALID_PROPOSAL_TYPES} sein",
            422,
        )

    if not rationale:
        return _err("VALIDATION_ERROR", "rationale darf nicht leer sein", 422)

    # Validate type-specific required fields
    if proposal_type in ("merge", "task_move") and not args.get("target_epic_key"):
        return _err("VALIDATION_ERROR", f"target_epic_key ist Pflicht für {proposal_type}", 422)

    if proposal_type == "task_move" and not args.get("task_keys"):
        return _err("VALIDATION_ERROR", "task_keys ist Pflicht für task_move", 422)

    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Verify source epic
                result = await db.execute(
                    select(Epic).where(Epic.epic_key == epic_key)
                )
                epic = result.scalar_one_or_none()
                if not epic:
                    return _err("ENTITY_NOT_FOUND", f"Epic '{epic_key}' nicht gefunden", 404)

                # Verify target epic if needed
                if args.get("target_epic_key"):
                    t_result = await db.execute(
                        select(Epic).where(Epic.epic_key == args["target_epic_key"])
                    )
                    if not t_result.scalar_one_or_none():
                        return _err(
                            "ENTITY_NOT_FOUND",
                            f"Target-Epic '{args['target_epic_key']}' nicht gefunden",
                            404,
                        )

                # Create a decision request as a restructure proposal
                payload = {
                    "type": "epic_restructure",
                    "proposal_type": proposal_type,
                    "epic_key": epic_key,
                    "rationale": rationale,
                    "target_epic_key": args.get("target_epic_key"),
                    "task_keys": args.get("task_keys", []),
                    "split_plan": args.get("split_plan"),
                    "code_node_refs": args.get("code_node_refs", []),
                    "state": "proposed",
                }

                dr = DecisionRequest(
                    task_id=None,  # Epic-level, not task-level
                    epic_id=epic.id,
                    owner_id=epic.owner_id or ADMIN_ID,
                    state="open",
                    payload=payload,
                )
                db.add(dr)
                await db.flush()
                await db.refresh(dr)

                # Notify admins
                publish(
                    "restructure_proposed",
                    {
                        "decision_request_id": str(dr.id),
                        "epic_key": epic_key,
                        "proposal_type": proposal_type,
                        "rationale": rationale,
                    },
                    channel="admin",
                )

                return _ok({
                    "data": {
                        "decision_request_id": str(dr.id),
                        "epic_key": epic_key,
                        "proposal_type": proposal_type,
                        "state": "proposed",
                    },
                })
    except Exception as exc:
        logger.exception("propose_epic_restructure failed")
        return _err("INTERNAL_ERROR", str(exc), 500)
