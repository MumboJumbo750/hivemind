"""GitHub/GitLab MCP Read Tools — TASK-8-009/010.

Read-only tools for agents to access GitHub/GitLab data via their REST APIs.

Tools:
  hivemind-get_github_pr           — GitHub Pull Request details
  hivemind-get_github_issue        — GitHub Issue details
  hivemind-get_github_check_status — GitHub Check Run status for a commit ref
  hivemind-get_gitlab_mr           — GitLab Merge Request details
  hivemind-get_gitlab_pipeline     — GitLab Pipeline status
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from typing import Any

import httpx
from mcp.types import TextContent, Tool

from app.config import settings
from app.mcp.server import register_tool

logger = logging.getLogger(__name__)


# ── API Helpers ─────────────────────────────────────────────────────────────

async def _github_get(path: str) -> dict[str, Any]:
    """Make an authenticated GET request to the GitHub API."""
    headers = {"Accept": "application/vnd.github+json"}
    if settings.hivemind_github_token:
        headers["Authorization"] = f"Bearer {settings.hivemind_github_token}"
    base = settings.hivemind_github_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}{path}", headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


async def _gitlab_get(path: str) -> dict[str, Any]:
    """Make an authenticated GET request to the GitLab API."""
    headers: dict[str, str] = {}
    if settings.hivemind_gitlab_token:
        headers["PRIVATE-TOKEN"] = settings.hivemind_gitlab_token
    base = settings.hivemind_gitlab_url.rstrip("/")
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{base}/api/v4{path}", headers=headers, timeout=10.0)
        resp.raise_for_status()
        return resp.json()


# ── Response helpers ─────────────────────────────────────────────────────────

def _ok(data: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"data": data}, default=str))]


def _err(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": msg}))]


# ── Tool: get_github_pr ──────────────────────────────────────────────────────

async def _handle_get_github_pr(args: dict) -> list[TextContent]:
    try:
        data = await _github_get(
            f"/repos/{args['owner']}/{args['repo']}/pulls/{args['pr_number']}"
        )
        return _ok(data)
    except Exception as exc:
        logger.error("get_github_pr error: %s", exc)
        return _err(str(exc))


register_tool(
    Tool(
        name="hivemind-get_github_pr",
        description="Get GitHub Pull Request details (read-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "pr_number": {"type": "integer", "description": "PR number"},
            },
            "required": ["owner", "repo", "pr_number"],
        },
    ),
    _handle_get_github_pr,
)


# ── Tool: get_github_issue ───────────────────────────────────────────────────

async def _handle_get_github_issue(args: dict) -> list[TextContent]:
    try:
        data = await _github_get(
            f"/repos/{args['owner']}/{args['repo']}/issues/{args['issue_number']}"
        )
        return _ok(data)
    except Exception as exc:
        logger.error("get_github_issue error: %s", exc)
        return _err(str(exc))


register_tool(
    Tool(
        name="hivemind-get_github_issue",
        description="Get GitHub Issue details (read-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "issue_number": {"type": "integer", "description": "Issue number"},
            },
            "required": ["owner", "repo", "issue_number"],
        },
    ),
    _handle_get_github_issue,
)


# ── Tool: get_github_check_status ───────────────────────────────────────────

async def _handle_get_github_check_status(args: dict) -> list[TextContent]:
    try:
        data = await _github_get(
            f"/repos/{args['owner']}/{args['repo']}/commits/{args['ref']}/check-runs"
        )
        return _ok(data)
    except Exception as exc:
        logger.error("get_github_check_status error: %s", exc)
        return _err(str(exc))


register_tool(
    Tool(
        name="hivemind-get_github_check_status",
        description="Get GitHub Check Run status for a commit (read-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "owner": {"type": "string", "description": "Repository owner"},
                "repo": {"type": "string", "description": "Repository name"},
                "ref": {
                    "type": "string",
                    "description": "Branch name, tag, or commit SHA",
                },
            },
            "required": ["owner", "repo", "ref"],
        },
    ),
    _handle_get_github_check_status,
)


# ── Tool: get_gitlab_mr ──────────────────────────────────────────────────────

async def _handle_get_gitlab_mr(args: dict) -> list[TextContent]:
    try:
        pid = urllib.parse.quote(str(args["project_id"]), safe="")
        data = await _gitlab_get(f"/projects/{pid}/merge_requests/{args['mr_iid']}")
        return _ok(data)
    except Exception as exc:
        logger.error("get_gitlab_mr error: %s", exc)
        return _err(str(exc))


register_tool(
    Tool(
        name="hivemind-get_gitlab_mr",
        description="Get GitLab Merge Request details (read-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "GitLab project ID or URL-encoded path (e.g. 'group/project')",
                },
                "mr_iid": {
                    "type": "integer",
                    "description": "MR internal ID (iid) within the project",
                },
            },
            "required": ["project_id", "mr_iid"],
        },
    ),
    _handle_get_gitlab_mr,
)


# ── Tool: get_gitlab_pipeline ────────────────────────────────────────────────

async def _handle_get_gitlab_pipeline(args: dict) -> list[TextContent]:
    try:
        pid = urllib.parse.quote(str(args["project_id"]), safe="")
        data = await _gitlab_get(f"/projects/{pid}/pipelines/{args['pipeline_id']}")
        return _ok(data)
    except Exception as exc:
        logger.error("get_gitlab_pipeline error: %s", exc)
        return _err(str(exc))


register_tool(
    Tool(
        name="hivemind-get_gitlab_pipeline",
        description="Get GitLab Pipeline status (read-only).",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "GitLab project ID or URL-encoded path",
                },
                "pipeline_id": {
                    "type": "integer",
                    "description": "Pipeline ID",
                },
            },
            "required": ["project_id", "pipeline_id"],
        },
    ),
    _handle_get_gitlab_pipeline,
)
