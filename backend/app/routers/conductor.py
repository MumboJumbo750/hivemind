"""Conductor API — Phase 8 (TASK-8-004) + TASK-IDE-005."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_user

router = APIRouter(prefix="/admin/conductor", tags=["conductor"])
ide_router = APIRouter(prefix="/conductor", tags=["conductor-ide"])


class ManualDispatchRequest(BaseModel):
    agent_role: str
    prompt: str | None = None
    task_key: str | None = None
    epic_id: str | None = None
    project_id: str | None = None


class CompleteDispatchRequest(BaseModel):
    status: Literal["completed", "failed", "cancelled", "timed_out"] = "completed"
    result: str | None = None
    error: str | None = None


class DispatchProgressRequest(BaseModel):
    stage: str
    message: str | None = None
    details: dict[str, Any] | None = None


def _parse_dispatch_id(dispatch_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(dispatch_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid dispatch_id") from exc


def _prompt_type_for_agent_role(agent_role: str) -> str:
    normalized = (agent_role or "").strip().lower()
    if normalized == "reviewer":
        return "review"
    return normalized or "worker"


async def _resolve_manual_prompt(
    body: ManualDispatchRequest,
    db: AsyncSession,
) -> tuple[str, str]:
    prompt_type = _prompt_type_for_agent_role(body.agent_role)
    has_context = bool(body.task_key or body.epic_id or body.project_id)

    if has_context:
        from app.services.prompt_generator import PromptGenerator

        try:
            prompt = await PromptGenerator(db).generate(
                prompt_type,
                task_id=body.task_key,
                epic_id=body.epic_id,
                project_id=body.project_id,
            )
            return prompt, "generated"
        except ValueError:
            # Fall back to explicit prompt when the selected role cannot be generated
            # from the supplied entity context alone.
            pass

    if body.prompt:
        return body.prompt, "provided"

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Prompt oder passende Entity-Referenz erforderlich.",
    )


@router.post("/dispatch")
async def manual_dispatch(
    body: ManualDispatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    del current_user
    from app.services.ai_provider import NeedsManualMode, get_provider
    from app.services.agentic_dispatch import agentic_dispatch

    try:
        provider = await get_provider(body.agent_role, db)
    except NeedsManualMode:
        return {
            "status": "no_provider",
            "message": f"Kein AI-Provider für Rolle '{body.agent_role}' konfiguriert.",
        }

    try:
        prompt, prompt_source = await _resolve_manual_prompt(body, db)
        result = await agentic_dispatch(
            provider=provider,
            prompt=prompt,
            agent_role=body.agent_role,
            task_key=body.task_key,
            epic_id=body.epic_id,
        )
        status = "completed" if not result.error else "partial"
        return {
            "status": status,
            "content": result.content,
            "tool_calls": [
                {
                    "name": tc["tool"],
                    "tool": tc["tool"],
                    "arguments": tc["arguments"],
                    "result_preview": tc.get("result_preview", ""),
                }
                for tc in result.tool_calls_executed
            ],
            "iterations": result.iterations,
            "input_tokens": result.total_input_tokens,
            "output_tokens": result.total_output_tokens,
            "model": result.model,
            "error": result.error,
            "prompt_source": prompt_source,
        }
    except Exception as exc:
        return {"status": "failed", "message": str(exc)}


@router.get("/dispatches")
async def list_dispatches(
    limit: int = Query(default=50, le=200),
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    del current_user
    from app.services.conductor import get_dispatches

    dispatches = await get_dispatches(db, limit=limit, status_filter=status)

    return [
        {
            "id": str(d.id),
            "trigger_type": d.trigger_type,
            "trigger_id": d.trigger_id,
            "trigger_detail": d.trigger_detail,
            "agent_role": d.agent_role,
            "prompt_type": d.prompt_type,
            "execution_mode": d.execution_mode,
            "status": d.status,
            "status_history": (d.result or {}).get("status_history") if isinstance(d.result, dict) else None,
            "governance": (d.result or {}).get("governance") if isinstance(d.result, dict) else None,
            "dispatched_at": d.dispatched_at.isoformat() if d.dispatched_at else None,
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
        }
        for d in dispatches
    ]


@router.get("/status")
async def conductor_status(current_user=Depends(get_current_user)):
    del current_user
    from app.config import settings

    return {
        "enabled": settings.hivemind_conductor_enabled,
        "parallel": settings.hivemind_conductor_parallel,
        "cooldown_seconds": settings.hivemind_conductor_cooldown_seconds,
        "ide_timeout_seconds": settings.conductor_ide_timeout_seconds,
    }


@ide_router.get("/dispatches/pending")
async def get_pending_ide_dispatches(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return open IDE dispatches for the VS Code extension."""
    del current_user
    from app.services.conductor import get_pending_ide_dispatches_from_db

    dispatches = await get_pending_ide_dispatches_from_db(db)
    items = []
    for dispatch in dispatches:
        payload = dispatch.result if isinstance(dispatch.result, dict) else {}
        items.append(
            {
                "dispatch_id": str(dispatch.id),
                "agent_role": dispatch.agent_role,
                "prompt_type": dispatch.prompt_type,
                "trigger_id": dispatch.trigger_id,
                "prompt": payload.get("prompt"),
                "tools_needed": payload.get("tools_needed") or ["hivemind-*"],
                "execution_mode": dispatch.execution_mode,
                "status": dispatch.status,
                "dispatched_at": dispatch.dispatched_at.isoformat() if dispatch.dispatched_at else None,
            }
        )
    return {"data": items}


@ide_router.post("/dispatches/{dispatch_id}/acknowledge")
async def acknowledge_ide_dispatch(
    dispatch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Extension confirms receipt: dispatched -> acknowledged."""
    del current_user
    from app.services.conductor import get_dispatch_by_id

    uid = _parse_dispatch_id(dispatch_id)
    dispatch = await get_dispatch_by_id(db, uid)
    if dispatch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch not found")

    if dispatch.status == "dispatched":
        existing = dict(dispatch.result) if isinstance(dispatch.result, dict) else {}
        existing["acknowledged_at"] = datetime.now(UTC).isoformat()
        dispatch.result = existing
        dispatch.status = "acknowledged"
        await db.commit()

    return {"status": dispatch.status, "dispatch_id": dispatch_id}


@ide_router.post("/dispatches/{dispatch_id}/running")
async def mark_ide_dispatch_running(
    dispatch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Extension reports execution start: acknowledged -> running."""
    del current_user
    from app.services.conductor import get_dispatch_by_id

    uid = _parse_dispatch_id(dispatch_id)
    dispatch = await get_dispatch_by_id(db, uid)
    if dispatch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch not found")

    if dispatch.status in {"dispatched", "acknowledged"}:
        existing = dict(dispatch.result) if isinstance(dispatch.result, dict) else {}
        existing["running_at"] = datetime.now(UTC).isoformat()
        dispatch.result = existing
        dispatch.status = "running"
        await db.commit()

    return {"status": dispatch.status, "dispatch_id": dispatch_id}


@ide_router.post("/dispatches/{dispatch_id}/complete")
async def complete_ide_dispatch(
    dispatch_id: str,
    body: CompleteDispatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Extension reports final result: running -> completed|failed."""
    del current_user
    from app.services.conductor import get_dispatch_by_id

    uid = _parse_dispatch_id(dispatch_id)
    dispatch = await get_dispatch_by_id(db, uid)
    if dispatch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch not found")

    result_payload = dict(dispatch.result) if isinstance(dispatch.result, dict) else {}
    if dispatch.status in {"dispatched", "acknowledged"}:
        result_payload["running_at"] = datetime.now(UTC).isoformat()
    if body.result is not None:
        result_payload["result"] = body.result
    if body.error is not None:
        result_payload["error"] = body.error
    elif body.status == "failed" and body.result:
        result_payload["error"] = body.result

    dispatch.result = result_payload
    dispatch.status = body.status
    dispatch.completed_at = datetime.now(UTC)
    await db.commit()
    return {"status": body.status, "dispatch_id": dispatch_id}


@ide_router.post("/dispatches/{dispatch_id}/progress")
async def report_ide_dispatch_progress(
    dispatch_id: str,
    body: DispatchProgressRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Extension reports progress events while a dispatch is being executed in IDE."""
    del current_user
    from app.services.conductor import get_dispatch_by_id

    uid = _parse_dispatch_id(dispatch_id)
    dispatch = await get_dispatch_by_id(db, uid)
    if dispatch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch not found")

    result_payload = dict(dispatch.result) if isinstance(dispatch.result, dict) else {}
    progress = result_payload.get("progress")
    if not isinstance(progress, list):
        progress = []

    entry: dict[str, Any] = {
        "at": datetime.now(UTC).isoformat(),
        "stage": body.stage,
    }
    if body.message is not None:
        entry["message"] = body.message
    if body.details is not None:
        entry["details"] = body.details

    progress.append(entry)
    result_payload["progress"] = progress[-200:]
    result_payload["last_progress_at"] = entry["at"]

    if dispatch.status in {"dispatched", "acknowledged"}:
        dispatch.status = "running"
        result_payload.setdefault("running_at", entry["at"])

    dispatch.result = result_payload
    await db.commit()
    return {"status": dispatch.status, "dispatch_id": dispatch_id, "progress_count": len(result_payload["progress"])}
