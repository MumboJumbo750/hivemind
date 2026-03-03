"""GitHub Actions Agent Service — Phase 8 (TASK-8-012).

3 operation modes:
1. AI-Provider mode: GitHub Actions Workflow calls GitHub Models API as AI provider
2. Guard mode: CI guards report results back via report_guard_result MCP tool
3. Agent-in-CI mode: full Hivemind agent runs in CI runner

This service handles:
- Triggering workflow dispatch via GitHub API
- Receiving guard results back from CI
"""
import logging
import uuid
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def dispatch_workflow(
    owner: str,
    repo: str,
    workflow_id: str,
    task_key: str,
    ref: str = "main",
    extra_inputs: dict | None = None,
) -> dict:
    """Trigger a GitHub Actions workflow dispatch.

    POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches
    """
    if not settings.hivemind_github_token:
        return {"error": "HIVEMIND_GITHUB_TOKEN not configured"}

    url = f"{settings.hivemind_github_url}/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches"
    inputs = {"task_key": task_key}
    if extra_inputs:
        inputs.update(extra_inputs)

    payload = {"ref": ref, "inputs": inputs}
    headers = {
        "Authorization": f"Bearer {settings.hivemind_github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code == 204:
                logger.info("Workflow dispatch triggered: %s/%s/%s for task %s", owner, repo, workflow_id, task_key)
                return {"status": "dispatched", "workflow": f"{owner}/{repo}/{workflow_id}", "task_key": task_key}
            else:
                logger.error("Workflow dispatch failed: %s %s", resp.status_code, resp.text)
                return {"error": f"GitHub API error {resp.status_code}", "detail": resp.text[:500]}
    except Exception as e:
        logger.error("Workflow dispatch exception: %s", e)
        return {"error": str(e)}


async def report_guard_result(
    task_key: str,
    guard_name: str,
    passed: bool,
    details: str | None,
    commit_sha: str | None,
    owner: str | None,
    repo: str | None,
    db: Any,
) -> dict:
    """Report a CI guard result back to Hivemind.

    Called by agents running in GitHub Actions CI.
    Optionally updates GitHub Commit Status.
    """
    from sqlalchemy import select
    from app.models.task import Task

    result = await db.execute(select(Task).where(Task.task_key == task_key))
    task = result.scalar_one_or_none()
    if not task:
        return {"error": f"Task '{task_key}' not found"}

    # Update commit status if commit_sha provided
    if commit_sha and owner and repo and settings.hivemind_github_token:
        await _update_commit_status(
            owner=owner,
            repo=repo,
            sha=commit_sha,
            guard_name=guard_name,
            passed=passed,
            details=details or "",
        )

    logger.info(
        "Guard result: task=%s, guard=%s, passed=%s",
        task_key, guard_name, passed,
    )

    return {
        "task_key": task_key,
        "guard_name": guard_name,
        "passed": passed,
        "recorded": True,
    }


async def _update_commit_status(
    owner: str,
    repo: str,
    sha: str,
    guard_name: str,
    passed: bool,
    details: str,
) -> None:
    """Update GitHub Commit Status."""
    url = f"{settings.hivemind_github_url}/repos/{owner}/{repo}/statuses/{sha}"
    payload = {
        "state": "success" if passed else "failure",
        "context": f"hivemind/{guard_name}",
        "description": details[:140] if details else ("Guard passed" if passed else "Guard failed"),
    }
    headers = {
        "Authorization": f"Bearer {settings.hivemind_github_token}",
        "Accept": "application/vnd.github+json",
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json=payload, headers=headers, timeout=10.0)
    except Exception as e:
        logger.warning("Failed to update commit status: %s", e)
