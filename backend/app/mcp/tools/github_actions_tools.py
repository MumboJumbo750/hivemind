"""GitHub Actions MCP Tools — Phase 8 (TASK-8-012).

report_guard_result: Called by agents running in GitHub Actions CI to report guard results.
"""
from __future__ import annotations

import json
import logging

from mcp.types import TextContent, Tool

from app.db import AsyncSessionLocal
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)


async def _report_guard_result_handler(args: dict) -> list[TextContent]:
    actor_id = args.get("_actor_id", "00000000-0000-0000-0000-000000000001")
    async with AsyncSessionLocal() as db:
        from app.services.github_actions import report_guard_result
        result = await report_guard_result(
            task_key=args["task_key"],
            guard_name=args["guard_name"],
            passed=bool(args["passed"]),
            details=args.get("details"),
            commit_sha=args.get("commit_sha"),
            owner=args.get("owner"),
            repo=args.get("repo"),
            db=db,
        )
    return [TextContent(type="text", text=json.dumps(result, default=str))]


register_tool(
    Tool(
        name="hivemind-report_guard_result",
        description=(
            "Report a CI guard result back to Hivemind from GitHub Actions. "
            "Called by agents running in CI pipelines. "
            "Optionally updates GitHub Commit Status."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task_key": {"type": "string", "description": "Task key (e.g. TASK-8-001)"},
                "guard_name": {"type": "string", "description": "Name of the guard (e.g. lint, test, security)"},
                "passed": {"type": "boolean", "description": "Whether the guard passed"},
                "details": {"type": "string", "description": "Guard output/details"},
                "commit_sha": {"type": "string", "description": "Git commit SHA (optional, for Commit Status)"},
                "owner": {"type": "string", "description": "GitHub repo owner"},
                "repo": {"type": "string", "description": "GitHub repo name"},
            },
            "required": ["task_key", "guard_name", "passed"],
        },
    ),
    _report_guard_result_handler,
)
