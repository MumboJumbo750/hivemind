"""Conductor-Orchestrator Service — Phase 8 (TASK-8-004 + TASK-8-005).

Event-driven dispatcher that reacts to state transitions and dispatches agents
to one of the configured execution modes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


VALID_EXECUTION_MODES = {"local", "github_actions", "ide", "byoai"}
DEFAULT_IDE_TOOLS = ["read_file", "write_file", "run_terminal", "hivemind/*"]


RULE_DEFAULTS: dict[str, str] = {
    "task_scoped_to_in_progress": "local",
    "task_in_progress_to_in_review": "local",
    "task_done": "local",
    "task_incoming_to_scoped": "local",
    "event_unrouted_inbound": "local",
    "epic_created": "local",
    "epic_scoped": "local",
    "epic_proposal_submitted": "local",
    "skill_proposal": "local",
    "project_created": "local",
    "push_event": "local",
    "decision_request_open": "local",
}


def _cooldown_key(agent_role: str, trigger_id: str, cooldown_seconds: int) -> str:
    bucket = int(time.time()) // max(cooldown_seconds, 1)
    return f"{agent_role}:{trigger_id}:{bucket}"


def _normalize_execution_mode(mode: str | None, default: str = "local") -> str:
    if not mode:
        return default
    normalized = mode.strip().lower()
    if normalized not in VALID_EXECUTION_MODES:
        return default
    return normalized


def _default_fallback_chain(execution_mode: str) -> list[str]:
    mode = _normalize_execution_mode(execution_mode)
    if mode == "ide":
        return ["ide", "local", "byoai"]
    if mode == "github_actions":
        return ["github_actions", "local", "byoai"]
    if mode == "byoai":
        return ["byoai"]
    return ["local", "byoai"]


def _normalize_fallback_chain(chain: Any, first_mode: str) -> list[str]:
    if not isinstance(chain, list):
        return _default_fallback_chain(first_mode)
    cleaned: list[str] = []
    for raw in chain:
        mode = _normalize_execution_mode(str(raw), default="")
        if mode and mode not in cleaned:
            cleaned.append(mode)
    if not cleaned:
        return _default_fallback_chain(first_mode)
    normalized_first = _normalize_execution_mode(first_mode)
    if normalized_first in cleaned:
        cleaned.remove(normalized_first)
    cleaned.insert(0, normalized_first)
    return cleaned


def _remaining_fallbacks(fallback_chain: list[str], current_mode: str) -> list[str]:
    mode = _normalize_execution_mode(current_mode)
    if mode not in fallback_chain:
        return []
    idx = fallback_chain.index(mode)
    return fallback_chain[idx + 1 :]


def _prompt_kind(agent_role: str, prompt_type: str) -> str:
    prefix = (prompt_type or "").split("_", 1)[0].strip().lower()
    if prefix == "reviewer":
        return "review"
    if prefix in {"worker", "gaertner", "kartograph", "stratege", "architekt", "triage"}:
        return prefix
    role = (agent_role or "").strip().lower()
    if role == "reviewer":
        return "review"
    if role in {"worker", "gaertner", "kartograph", "stratege", "architekt", "triage"}:
        return role
    return "worker"


class ConductorService:
    """Event-driven agent dispatcher."""

    def __init__(self):
        self._semaphore: asyncio.Semaphore | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        from app.config import settings

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.hivemind_conductor_parallel)
        return self._semaphore

    @staticmethod
    def _merge_result(current: Any, updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current) if isinstance(current, dict) else {}
        merged.update(updates)
        return merged

    async def _is_cooldown_active(self, cooldown_key: str, db: Any) -> bool:
        from sqlalchemy import select

        from app.models.conductor import ConductorDispatch

        result = await db.execute(
            select(ConductorDispatch).where(
                ConductorDispatch.cooldown_key == cooldown_key,
                ConductorDispatch.status.in_(["dispatched", "acknowledged", "running"]),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _record_dispatch(
        self,
        db: Any,
        trigger_type: str,
        trigger_id: str,
        trigger_detail: str,
        agent_role: str,
        prompt_type: str,
        execution_mode: str,
        cooldown_key: str,
        *,
        status: str = "dispatched",
        result: dict[str, Any] | None = None,
    ) -> Any:
        from app.models.conductor import ConductorDispatch

        dispatch = ConductorDispatch(
            id=uuid.uuid4(),
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            trigger_detail=trigger_detail,
            agent_role=agent_role,
            prompt_type=prompt_type,
            execution_mode=execution_mode,
            status=status,
            cooldown_key=cooldown_key,
            result=result,
            dispatched_at=datetime.now(UTC),
        )
        db.add(dispatch)
        await db.flush()
        await db.refresh(dispatch)
        return dispatch

    async def _update_dispatch(
        self,
        db: Any,
        dispatch: Any,
        *,
        status: str,
        result: dict[str, Any] | None = None,
        mark_completed: bool = False,
    ) -> None:
        dispatch.status = status
        if result is not None:
            dispatch.result = result
        if mark_completed:
            dispatch.completed_at = datetime.now(UTC)
        await db.flush()

    async def _resolve_rule_dispatch_config(
        self,
        db: Any,
        rule_key: str,
        *,
        default_mode: str = "local",
    ) -> tuple[str, list[str]]:
        from sqlalchemy import select

        from app.models.settings import AppSettings

        fallback_mode = RULE_DEFAULTS.get(rule_key, default_mode)
        mode = _normalize_execution_mode(fallback_mode)
        fallback_chain = _default_fallback_chain(mode)

        result = await db.execute(
            select(AppSettings).where(AppSettings.key == "conductor_dispatch_rules")
        )
        row = result.scalar_one_or_none()
        if row is None or not row.value:
            return mode, fallback_chain

        try:
            parsed = json.loads(row.value) if isinstance(row.value, str) else row.value
        except Exception:
            logger.warning("Invalid conductor_dispatch_rules JSON, using defaults")
            return mode, fallback_chain

        if not isinstance(parsed, dict):
            return mode, fallback_chain

        raw_rule = parsed.get(rule_key)
        if isinstance(raw_rule, str):
            mode = _normalize_execution_mode(raw_rule, default=mode)
            return mode, _default_fallback_chain(mode)
        if isinstance(raw_rule, dict):
            mode = _normalize_execution_mode(raw_rule.get("execution_mode"), default=mode)
            chain = _normalize_fallback_chain(raw_rule.get("fallback_chain"), mode)
            return mode, chain

        return mode, fallback_chain

    async def _build_prompt(
        self,
        db: Any,
        *,
        trigger_id: str,
        trigger_detail: str,
        agent_role: str,
        prompt_type: str,
    ) -> str:
        from app.services.prompt_generator import PromptGenerator

        fallback_prompt = f"[{prompt_type}] Trigger: {trigger_detail}\nTask/Entity ID: {trigger_id}"
        try:
            generator = PromptGenerator(db)
            return await generator.generate(
                _prompt_kind(agent_role, prompt_type),
                task_id=trigger_id,
            )
        except Exception:
            return fallback_prompt

    async def dispatch(
        self,
        trigger_type: str,
        trigger_id: str,
        trigger_detail: str,
        agent_role: str,
        prompt_type: str,
        db: Any,
        execution_mode: str = "local",
        fallback_chain: list[str] | None = None,
        source_dispatch_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a single agent and persist full lifecycle states."""
        from app.config import settings

        if not settings.hivemind_conductor_enabled:
            return {"status": "conductor_disabled", "byoai": True}

        normalized_mode = _normalize_execution_mode(execution_mode)
        normalized_chain = _normalize_fallback_chain(
            fallback_chain or _default_fallback_chain(normalized_mode),
            normalized_mode,
        )

        cooldown_s = settings.hivemind_conductor_cooldown_seconds
        ck = _cooldown_key(agent_role, trigger_id, cooldown_s)

        if await self._is_cooldown_active(ck, db):
            logger.debug("Conductor: cooldown active for %s/%s — skipping", agent_role, trigger_id)
            dispatch = await self._record_dispatch(
                db,
                trigger_type,
                trigger_id,
                trigger_detail,
                agent_role,
                prompt_type,
                normalized_mode,
                ck,
                status="cooldown_skipped",
                result={"fallback_chain": normalized_chain},
            )
            await db.commit()
            return {"status": "cooldown_skipped", "dispatch_id": str(dispatch.id)}

        initial_result: dict[str, Any] = {"fallback_chain": normalized_chain}
        if source_dispatch_id:
            initial_result["source_dispatch_id"] = source_dispatch_id

        dispatch = await self._record_dispatch(
            db,
            trigger_type,
            trigger_id,
            trigger_detail,
            agent_role,
            prompt_type,
            normalized_mode,
            ck,
            result=initial_result,
        )
        await db.commit()

        async with self._get_semaphore():
            try:
                if normalized_mode == "ide":
                    from app.services import event_bus

                    full_prompt = await self._build_prompt(
                        db,
                        trigger_id=trigger_id,
                        trigger_detail=trigger_detail,
                        agent_role=agent_role,
                        prompt_type=prompt_type,
                    )
                    event_payload = {
                        "dispatch_id": str(dispatch.id),
                        "agent_role": agent_role,
                        "prompt_type": prompt_type,
                        "trigger_id": trigger_id,
                        "prompt": full_prompt,
                        "tools_needed": DEFAULT_IDE_TOOLS,
                        "execution_mode": "ide",
                    }
                    dispatch.result = self._merge_result(
                        dispatch.result,
                        {
                            "prompt": full_prompt,
                            "tools_needed": DEFAULT_IDE_TOOLS,
                            "event_type": "conductor:dispatch",
                        },
                    )
                    await db.commit()
                    event_bus.publish("conductor:dispatch", event_payload, channel="tasks")
                    logger.info("Conductor: IDE dispatch queued via SSE for %s/%s", agent_role, trigger_id)
                    return {"status": "ide_dispatched", "dispatch_id": str(dispatch.id)}

                if normalized_mode == "byoai":
                    result_payload = self._merge_result(dispatch.result, {"byoai": True})
                    await self._update_dispatch(
                        db,
                        dispatch,
                        status="byoai",
                        result=result_payload,
                        mark_completed=True,
                    )
                    await db.commit()
                    return {"status": "byoai", "dispatch_id": str(dispatch.id)}

                if normalized_mode == "github_actions":
                    from app.services.github_actions import dispatch_workflow

                    ga_config = getattr(settings, "hivemind_github_actions_config", {}) or {}
                    await self._update_dispatch(db, dispatch, status="running")
                    await db.commit()

                    ga_result = await dispatch_workflow(
                        owner=ga_config.get("owner", ""),
                        repo=ga_config.get("repo", ""),
                        workflow_id=ga_config.get("workflow_id", "hivemind-agent.yml"),
                        task_key=trigger_id,
                        extra_inputs={"agent_role": agent_role, "prompt_type": prompt_type},
                    )
                    success = "error" not in ga_result
                    final_status = "completed" if success else "failed"
                    await self._update_dispatch(
                        db,
                        dispatch,
                        status=final_status,
                        result=self._merge_result(dispatch.result, ga_result),
                        mark_completed=True,
                    )
                    await db.commit()
                    return {"status": final_status, "dispatch_id": str(dispatch.id), **ga_result}

                from app.services.ai_provider import NeedsManualMode, get_provider, send_with_retry

                await self._update_dispatch(db, dispatch, status="running")
                await db.commit()

                try:
                    provider = await get_provider(agent_role, db)
                except NeedsManualMode:
                    await self._update_dispatch(
                        db,
                        dispatch,
                        status="byoai",
                        result=self._merge_result(
                            dispatch.result,
                            {"byoai": True, "reason": "no_provider_configured"},
                        ),
                        mark_completed=True,
                    )
                    await db.commit()
                    logger.info("Conductor: no provider for %s → BYOAI", agent_role)
                    return {"status": "byoai", "dispatch_id": str(dispatch.id)}

                prompt = await self._build_prompt(
                    db,
                    trigger_id=trigger_id,
                    trigger_detail=trigger_detail,
                    agent_role=agent_role,
                    prompt_type=prompt_type,
                )
                try:
                    response = await send_with_retry(
                        provider=provider,
                        prompt=prompt,
                        agent_role=agent_role,
                    )
                except Exception as exc:
                    remaining = _remaining_fallbacks(normalized_chain, "local")
                    if remaining and remaining[0] == "byoai":
                        await self._update_dispatch(
                            db,
                            dispatch,
                            status="byoai",
                            result=self._merge_result(
                                dispatch.result,
                                {"byoai": True, "local_error": str(exc)},
                            ),
                            mark_completed=True,
                        )
                        await db.commit()
                        return {"status": "byoai", "dispatch_id": str(dispatch.id)}
                    raise

                result_payload = {
                    "content": response.content,
                    "tool_calls": [
                        {"name": tc.name, "arguments": tc.arguments}
                        for tc in response.tool_calls
                    ],
                    "input_tokens": response.input_tokens,
                    "output_tokens": response.output_tokens,
                }
                await self._update_dispatch(
                    db,
                    dispatch,
                    status="completed",
                    result=self._merge_result(dispatch.result, result_payload),
                    mark_completed=True,
                )
                await db.commit()
                logger.info(
                    "Conductor: dispatched %s/%s → %s tokens",
                    agent_role,
                    prompt_type,
                    response.output_tokens,
                )
                return {"status": "completed", "dispatch_id": str(dispatch.id), **result_payload}

            except Exception as exc:
                await self._update_dispatch(
                    db,
                    dispatch,
                    status="failed",
                    result=self._merge_result(dispatch.result, {"error": str(exc)}),
                    mark_completed=True,
                )
                await db.commit()
                logger.error("Conductor dispatch failed for %s/%s: %s", agent_role, trigger_id, exc)
                return {"status": "failed", "dispatch_id": str(dispatch.id), "error": str(exc)}

    async def on_task_state_change(
        self, task_key: str, task_id: str, old_state: str, new_state: str, db: Any
    ) -> None:
        """React to task state transitions (Rules 1-4)."""
        from app.services.governance import get_governance_level

        del task_id

        if old_state == "scoped" and new_state == "in_progress":
            mode, chain = await self._resolve_rule_dispatch_config(db, "task_scoped_to_in_progress")
            await self.dispatch(
                trigger_type="task_state",
                trigger_id=task_key,
                trigger_detail=f"state:{old_state}->{new_state}",
                agent_role="worker",
                prompt_type="worker_implement",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

        elif old_state == "in_progress" and new_state == "in_review":
            level = await get_governance_level(db, "review")
            if level != "manual":
                mode, chain = await self._resolve_rule_dispatch_config(
                    db, "task_in_progress_to_in_review"
                )
                await self.dispatch(
                    trigger_type="task_state",
                    trigger_id=task_key,
                    trigger_detail=f"state:{old_state}->{new_state}",
                    agent_role="reviewer",
                    prompt_type="reviewer_check",
                    db=db,
                    execution_mode=mode,
                    fallback_chain=chain,
                )

        elif new_state == "done":
            mode, chain = await self._resolve_rule_dispatch_config(db, "task_done")
            await self.dispatch(
                trigger_type="task_state",
                trigger_id=task_key,
                trigger_detail=f"state:{old_state}->{new_state}",
                agent_role="gaertner",
                prompt_type="gaertner_harvest",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

        elif old_state == "incoming" and new_state == "scoped":
            level = await get_governance_level(db, "epic_scoping")
            if level != "manual":
                mode, chain = await self._resolve_rule_dispatch_config(
                    db, "task_incoming_to_scoped"
                )
                await self.dispatch(
                    trigger_type="task_state",
                    trigger_id=task_key,
                    trigger_detail=f"state:{old_state}->{new_state}",
                    agent_role="architekt",
                    prompt_type="architekt_decompose",
                    db=db,
                    execution_mode=mode,
                    fallback_chain=chain,
                )

    async def on_inbound_event(self, event_id: str, event_type: str, db: Any) -> None:
        """Rule 5: Unrouted inbound event -> Triage."""
        mode, chain = await self._resolve_rule_dispatch_config(db, "event_unrouted_inbound")
        await self.dispatch(
            trigger_type="event",
            trigger_id=event_id,
            trigger_detail=f"event_type:{event_type}",
            agent_role="triage",
            prompt_type="triage_classify",
            db=db,
            execution_mode=mode,
            fallback_chain=chain,
        )

    async def on_epic_created(self, epic_id: str, db: Any) -> None:
        """Rule 6: New epic -> Stratege (if epic_scoping!=manual)."""
        from app.services.governance import get_governance_level

        level = await get_governance_level(db, "epic_scoping")
        if level != "manual":
            mode, chain = await self._resolve_rule_dispatch_config(db, "epic_created")
            await self.dispatch(
                trigger_type="epic_state",
                trigger_id=epic_id,
                trigger_detail="epic:created",
                agent_role="stratege",
                prompt_type="stratege_plan",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

    async def on_epic_scoped(self, epic_id: str, db: Any) -> None:
        """Rule 7: Epic scoped -> Architekt."""
        mode, chain = await self._resolve_rule_dispatch_config(db, "epic_scoped")
        await self.dispatch(
            trigger_type="epic_state",
            trigger_id=epic_id,
            trigger_detail="state:incoming->scoped",
            agent_role="architekt",
            prompt_type="architekt_decompose",
            db=db,
            execution_mode=mode,
            fallback_chain=chain,
        )

    async def on_epic_proposal_submitted(self, proposal_id: str, db: Any) -> None:
        """Rule 8: Epic proposal -> Triage (if epic_proposal!=manual)."""
        from app.services.governance import get_governance_level

        level = await get_governance_level(db, "epic_proposal")
        if level != "manual":
            mode, chain = await self._resolve_rule_dispatch_config(db, "epic_proposal_submitted")
            await self.dispatch(
                trigger_type="event",
                trigger_id=proposal_id,
                trigger_detail="epic_proposal:submitted",
                agent_role="triage",
                prompt_type="triage_classify",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

    async def on_skill_proposal(self, skill_id: str, db: Any) -> None:
        """Rule 9: Skill proposal -> Gaertner (if skill_merge!=manual)."""
        from app.services.governance import get_governance_level

        level = await get_governance_level(db, "skill_merge")
        if level != "manual":
            mode, chain = await self._resolve_rule_dispatch_config(db, "skill_proposal")
            await self.dispatch(
                trigger_type="event",
                trigger_id=skill_id,
                trigger_detail="skill:proposal",
                agent_role="gaertner",
                prompt_type="gaertner_skill",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

    async def on_project_created(self, project_id: str, db: Any) -> None:
        """Rule 10: Project created -> Kartograph."""
        mode, chain = await self._resolve_rule_dispatch_config(db, "project_created")
        await self.dispatch(
            trigger_type="event",
            trigger_id=project_id,
            trigger_detail="project:created",
            agent_role="kartograph",
            prompt_type="kartograph_explore",
            db=db,
            execution_mode=mode,
            fallback_chain=chain,
        )

    async def on_push_event(self, repo: str, push_id: str, db: Any) -> None:
        """Rule 11: Push event -> Kartograph follow-up."""
        mode, chain = await self._resolve_rule_dispatch_config(db, "push_event")
        await self.dispatch(
            trigger_type="event",
            trigger_id=push_id,
            trigger_detail=f"push:{repo}",
            agent_role="kartograph",
            prompt_type="kartograph_follow_up",
            db=db,
            execution_mode=mode,
            fallback_chain=chain,
        )

    async def on_decision_request(self, decision_id: str, db: Any) -> None:
        """Rule 12: Decision request -> Resolver (if decision_request!=manual)."""
        from app.services.governance import get_governance_level

        level = await get_governance_level(db, "decision_request")
        if level != "manual":
            mode, chain = await self._resolve_rule_dispatch_config(db, "decision_request_open")
            await self.dispatch(
                trigger_type="event",
                trigger_id=decision_id,
                trigger_detail="decision_request:open",
                agent_role="architekt",
                prompt_type="architekt_resolve",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )


conductor = ConductorService()


async def conductor_poll_job() -> None:
    """Periodic conductor poll: check unrouted inbound events and dispatch triage."""
    from sqlalchemy import select

    from app.config import settings
    from app.db import AsyncSessionLocal
    from app.models.sync import SyncOutbox

    if not settings.hivemind_conductor_enabled:
        return

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(SyncOutbox).where(
                SyncOutbox.direction == "inbound",
                SyncOutbox.routing_state == "unrouted",
            ).limit(10)
        )
        entries = result.scalars().all()
        for entry in entries:
            try:
                await conductor.on_inbound_event(
                    event_id=str(entry.id),
                    event_type=entry.entity_type or "unknown",
                    db=db,
                )
            except Exception as exc:
                logger.error("Conductor poll error for entry %s: %s", entry.id, exc)
