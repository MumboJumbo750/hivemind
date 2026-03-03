"""Conductor IDE Dispatch Timeout Job — TASK-IDE-005.

Dispatches that stay in ``dispatched`` (no acknowledge) beyond timeout are
marked ``timed_out`` and re-dispatched via fallback chain (ide -> local -> byoai).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.conductor import ConductorDispatch
from app.services.conductor import conductor

logger = logging.getLogger(__name__)


async def ide_timeout_job() -> None:
    """Timeout IDE dispatches and trigger fallback dispatches."""
    from app.config import settings

    timeout_s = settings.conductor_ide_timeout_seconds
    cutoff = datetime.now(UTC) - timedelta(seconds=timeout_s)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ConductorDispatch).where(
                ConductorDispatch.execution_mode == "ide",
                ConductorDispatch.status == "dispatched",
                ConductorDispatch.dispatched_at < cutoff,
            )
        )
        timed_out = result.scalars().all()
        if not timed_out:
            return

        now = datetime.now(UTC)
        fallback_payloads: list[dict[str, str | list[str]]] = []

        for dispatch in timed_out:
            existing = dict(dispatch.result) if isinstance(dispatch.result, dict) else {}
            fallback_chain = existing.get("fallback_chain")
            if not isinstance(fallback_chain, list):
                fallback_chain = ["ide", "local", "byoai"]

            if "ide" in fallback_chain:
                next_chain = fallback_chain[fallback_chain.index("ide") + 1 :]
            else:
                next_chain = [mode for mode in fallback_chain if mode != "ide"]
            if not next_chain:
                next_chain = ["local", "byoai"]

            dispatch.status = "timed_out"
            dispatch.completed_at = now
            dispatch.result = {
                **existing,
                "error": "IDE dispatch timed out - no acknowledgement received",
                "timeout_seconds": timeout_s,
                "fallback_dispatched": next_chain[0],
                "fallback_chain_remaining": next_chain,
            }

            fallback_payloads.append(
                {
                    "source_dispatch_id": str(dispatch.id),
                    "trigger_type": dispatch.trigger_type,
                    "trigger_id": dispatch.trigger_id,
                    "trigger_detail": dispatch.trigger_detail or "",
                    "agent_role": dispatch.agent_role,
                    "prompt_type": dispatch.prompt_type or "",
                    "execution_mode": next_chain[0],
                    "fallback_chain": next_chain,
                }
            )
            logger.warning(
                "IDE dispatch timed out: %s [%s/%s] -> fallback %s",
                dispatch.id,
                dispatch.agent_role,
                dispatch.trigger_id,
                next_chain[0],
            )

        await db.commit()

        for payload in fallback_payloads:
            await conductor.dispatch(
                trigger_type=str(payload["trigger_type"]),
                trigger_id=str(payload["trigger_id"]),
                trigger_detail=str(payload["trigger_detail"]),
                agent_role=str(payload["agent_role"]),
                prompt_type=str(payload["prompt_type"]),
                db=db,
                execution_mode=str(payload["execution_mode"]),
                fallback_chain=list(payload["fallback_chain"]),  # type: ignore[arg-type]
                source_dispatch_id=str(payload["source_dispatch_id"]),
            )

        logger.info("IDE timeout job: %d dispatch(es) timed out and redispatched", len(timed_out))
