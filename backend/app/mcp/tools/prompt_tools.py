"""MCP Prompt Tool — TASK-3-005.

Tool:
  hivemind-get_prompt — Generate agent-specific prompt
"""
from __future__ import annotations

import json
import uuid

from mcp.types import TextContent, Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool
from app.services.prompt_generator import PromptGenerator, count_tokens


async def _handle_get_prompt(args: dict) -> list[TextContent]:
    """Generate a prompt for the specified agent type."""
    prompt_type = args.get("type", "")
    task_id = args.get("task_key") or args.get("task_id")
    epic_id = args.get("epic_id")
    project_id = args.get("project_id")
    requirement_text = args.get("requirement_text")
    priority_hint = args.get("priority_hint")

    valid_types = {"bibliothekar", "worker", "review", "gaertner", "architekt", "stratege", "stratege_requirement", "kartograph", "triage"}
    if prompt_type not in valid_types:
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": {
                    "code": "invalid_prompt_type",
                    "message": f"Unbekannter Prompt-Typ: '{prompt_type}'. Gültig: {', '.join(sorted(valid_types))}",
                }
            }),
        )]

    actor_id = None
    raw_actor = args.get("_actor_id")
    if raw_actor:
        try:
            actor_id = uuid.UUID(str(raw_actor))
        except ValueError:
            pass

    try:
        async with AsyncSessionLocal() as db:
            generator = PromptGenerator(db)
            prompt = await generator.generate(
                prompt_type,
                task_id=task_id,
                epic_id=epic_id,
                project_id=project_id,
                requirement_text=requirement_text,
                priority_hint=priority_hint,
                actor_id=actor_id,
            )
            await db.commit()

            tokens = count_tokens(prompt)
            return [TextContent(
                type="text",
                text=json.dumps({
                    "data": {
                        "prompt_type": prompt_type,
                        "prompt": prompt,
                        "token_count": tokens,
                    }
                }, default=str),
            )]
    except ValueError as exc:
        return [TextContent(
            type="text",
            text=json.dumps({"error": {"code": "validation_error", "message": str(exc)}}),
        )]


register_tool(
    Tool(
        name="hivemind-get_prompt",
        description="Agent-spezifischen Prompt generieren (bibliothekar, worker, review, gaertner, architekt, stratege, stratege_requirement, kartograph, triage).",
        inputSchema={
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "description": "Prompt-Typ: bibliothekar|worker|review|gaertner|architekt|stratege|stratege_requirement|kartograph|triage",
                    "enum": ["bibliothekar", "worker", "review", "gaertner", "architekt", "stratege", "stratege_requirement", "kartograph", "triage"],
                },
                "task_key": {"type": "string", "description": "Task-Key (z.B. 'TASK-88') — bevorzugt für bibliothekar, worker, review"},
                "task_id": {"type": "string", "description": "Legacy-Alias für task_key; weiter unterstützt"},
                "epic_id": {"type": "string", "description": "Epic-Key (z.B. 'EPIC-12') — Pflicht für architekt"},
                "project_id": {"type": "string", "description": "Project UUID — Pflicht für stratege"},
                "requirement_text": {"type": "string", "description": "Freitext-Anforderung — Pflicht für stratege_requirement"},
                "priority_hint": {"type": "string", "description": "Optionaler Prioritäts-Hinweis für stratege_requirement"},
            },
            "required": ["type"],
        },
    ),
    _handle_get_prompt,
)
