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
DEFAULT_IDE_TOOLS = ["read_file", "write_file", "run_terminal", "hivemind-*"]


RULE_DEFAULTS: dict[str, str] = {
    "task_scoped_to_in_progress": "local",
    "task_in_progress_to_in_review": "local",
    "task_done": "local",
    "task_qa_failed": "local",
    "task_escalated": "local",
    "task_incoming_to_scoped": "local",
    "event_unrouted_inbound": "local",
    "epic_created": "local",
    "epic_scoped": "local",
    "epic_proposal_submitted": "local",
    "skill_proposal": "local",
    "guard_proposal": "local",
    "epic_restructure_proposed": "local",
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
    pt = (prompt_type or "").strip().lower()
    if pt == "agentic_worker":
        return "agentic_worker"
    prefix = pt.split("_", 1)[0]
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


def _prompt_context_for_dispatch(
    *,
    trigger_type: str,
    trigger_id: str,
    trigger_detail: str,
    agent_role: str,
    prompt_type: str,
) -> dict[str, str]:
    """Map a dispatch trigger to PromptGenerator kwargs when possible."""
    kind = _prompt_kind(agent_role, prompt_type)

    if kind in {"worker", "review", "agentic_worker"}:
        return {"task_id": trigger_id}

    if kind == "gaertner":
        if trigger_type == "task_state":
            return {"task_id": trigger_id}
        if trigger_type == "epic_state":
            return {"epic_id": trigger_id}
        return {}

    if kind == "architekt" and trigger_type == "epic_state":
        return {"epic_id": trigger_id}

    if kind == "stratege" and trigger_detail == "project:created":
        return {"project_id": trigger_id}

    if kind == "triage":
        if trigger_detail == "epic_proposal:submitted":
            return {"proposal_id": trigger_id}
        if trigger_detail == "skill:proposal":
            return {"skill_id": trigger_id}
        if trigger_detail == "guard:proposal":
            return {"guard_id": trigger_id}
        if trigger_detail in {"decision_request:open", "epic_restructure:proposed"}:
            return {"decision_id": trigger_id}

    return {}


class ConductorService:
    """Event-driven agent dispatcher."""

    def __init__(self):
        self._semaphore: asyncio.Semaphore | None = None
        self._role_semaphores: dict[str, asyncio.Semaphore] = {}

    def _get_semaphore(self) -> asyncio.Semaphore:
        from app.config import settings

        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.hivemind_conductor_parallel)
        return self._semaphore

    def _get_role_semaphore(self, agent_role: str, max_parallel: int) -> asyncio.Semaphore:
        """Return a per-role semaphore keyed by role + max_parallel limit."""
        key = f"{agent_role}:{max(max_parallel, 1)}"
        if key not in self._role_semaphores:
            self._role_semaphores[key] = asyncio.Semaphore(max(max_parallel, 1))
        return self._role_semaphores[key]

    @staticmethod
    def _merge_result(current: Any, updates: dict[str, Any]) -> dict[str, Any]:
        merged = dict(current) if isinstance(current, dict) else {}
        merged.update(updates)
        return merged

    @staticmethod
    def _append_status_history(
        current: dict[str, Any] | None,
        status: str,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        merged = dict(current) if isinstance(current, dict) else {}
        history = merged.get("status_history")
        if not isinstance(history, list):
            history = []
        event = {"status": status, "at": datetime.now(UTC).isoformat()}
        if extra:
            event.update(extra)
        history.append(event)
        merged["status_history"] = history[-50:]
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
        if result is None:
            result = dict(dispatch.result) if isinstance(dispatch.result, dict) else {}
        dispatch.result = self._append_status_history(
            result,
            status,
            {"completed": mark_completed},
        )
        if mark_completed:
            dispatch.completed_at = datetime.now(UTC)
        await db.flush()

    async def _resolve_governance_payload(self, db: Any, prompt_type: str) -> dict[str, Any] | None:
        from app.services.governance import get_governance_level
        from app.services.governance_recommendations import get_governed_prompt

        governed = get_governed_prompt(prompt_type)
        if not governed:
            return None
        level = await get_governance_level(db, governed["governance_type"])
        payload = dict(governed)
        payload["level"] = level
        return payload

    async def _apply_governance_outcome(
        self,
        db: Any,
        *,
        dispatch: Any,
        prompt_type: str,
        trigger_id: str,
        agent_role: str,
        result_payload: dict[str, Any],
    ) -> dict[str, Any]:
        from app.services.governance_recommendations import (
            infer_recommended_action,
            store_governance_recommendation,
        )
        from app.services.learning_artifacts import create_learning_artifact

        governance = result_payload.get("governance")
        if not isinstance(governance, dict):
            return result_payload

        decisive_tools = set(governance.get("decisive_tools") or [])
        tool_calls = result_payload.get("tool_calls") or []
        decisive_called = [
            call.get("tool")
            for call in tool_calls
            if call.get("tool") in decisive_tools
        ]
        governance["decisive_tool_called"] = bool(decisive_called)
        if decisive_called:
            governance["decisive_tools_used"] = decisive_called
            result_payload["governance"] = governance
            return result_payload

        level = governance.get("level")
        if level not in {"assisted", "auto"}:
            result_payload["governance"] = governance
            return result_payload

        recommendation = await store_governance_recommendation(
            db,
            governance_type=str(governance["governance_type"]),
            governance_level=str(level),
            target_type=str(governance["target_type"]),
            target_ref=trigger_id,
            agent_role=agent_role,
            prompt_type=prompt_type,
            rationale=result_payload.get("content"),
            action=infer_recommended_action(
                str(governance["governance_type"]),
                result_payload.get("content"),
            ),
            dispatch_id=str(dispatch.id),
            payload={
                "tool_calls": tool_calls,
                "dispatch_context": result_payload.get("dispatch_context"),
                "fallback_chain": result_payload.get("fallback_chain"),
            },
            status="pending_human" if level == "assisted" else "auto_fallback",
        )
        if recommendation is not None:
            governance["recommendation_id"] = str(recommendation.id)
            if level == "assisted":
                governance["human_confirmation_required"] = True
            else:
                governance["fallback_to"] = "assisted"

            await create_learning_artifact(
                db,
                artifact_type="governance_recommendation",
                source_type="governance",
                source_ref=str(recommendation.id),
                source_dispatch_id=str(dispatch.id),
                agent_role=agent_role,
                project_id=(result_payload.get("dispatch_context") or {}).get("project_id"),
                epic_id=(result_payload.get("dispatch_context") or {}).get("epic_id"),
                task_id=(result_payload.get("dispatch_context") or {}).get("task_id"),
                summary=(result_payload.get("content") or "")[:1200],
                detail={
                    "governance_type": governance["governance_type"],
                    "governance_level": level,
                    "target_type": governance["target_type"],
                    "target_ref": trigger_id,
                },
                confidence=None,
            )
        result_payload["governance"] = governance
        return result_payload

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
        trigger_type: str,
        agent_role: str,
        prompt_type: str,
        thread_context: dict[str, Any] | None = None,
    ) -> str:
        from app.services.prompt_generator import PromptGenerator

        fallback_prompt = f"[{prompt_type}] Trigger: {trigger_detail}\nTask/Entity ID: {trigger_id}"
        prompt_kwargs = _prompt_context_for_dispatch(
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            trigger_detail=trigger_detail,
            agent_role=agent_role,
            prompt_type=prompt_type,
        )
        try:
            generator = PromptGenerator(db)
            return await generator.generate(_prompt_kind(agent_role, prompt_type), **prompt_kwargs)
        except Exception:
            if thread_context and thread_context.get("prompt_block"):
                return f"{fallback_prompt}\n\n{thread_context['prompt_block']}"
            return fallback_prompt

    async def _resolve_dispatch_context(
        self,
        db: Any,
        *,
        trigger_type: str,
        trigger_id: str,
        trigger_detail: str,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {
            "trigger_type": trigger_type,
            "trigger_id": trigger_id,
            "trigger_detail": trigger_detail,
        }
        try:
            if trigger_type == "task_state":
                from sqlalchemy import select

                from app.models.epic import Epic
                from app.models.project import Project
                from app.models.task import Task

                task = (await db.execute(select(Task).where(Task.task_key == trigger_id))).scalar_one_or_none()
                try:
                    if task is None:
                        task = (
                            await db.execute(select(Task).where(Task.id == uuid.UUID(trigger_id)))
                        ).scalar_one_or_none()
                except ValueError:
                    pass
                if task is None:
                    return context
                context.update({"task_key": task.task_key, "task_id": str(task.id)})
                epic = (await db.execute(select(Epic).where(Epic.id == task.epic_id))).scalar_one_or_none()
                if epic is None:
                    return context
                context["epic_id"] = str(epic.id)
                project = (await db.execute(select(Project).where(Project.id == epic.project_id))).scalar_one_or_none()
                if project:
                    context.update(self._project_context(project))
                return context

            if trigger_type == "epic_state":
                from sqlalchemy import select

                from app.models.epic import Epic
                from app.models.project import Project

                epic = (await db.execute(select(Epic).where(Epic.id == uuid.UUID(trigger_id)))).scalar_one_or_none()
                if epic is None:
                    return context
                context["epic_id"] = str(epic.id)
                project = (await db.execute(select(Project).where(Project.id == epic.project_id))).scalar_one_or_none()
                if project:
                    context.update(self._project_context(project))
                return context

            if trigger_type == "event":
                from sqlalchemy import select

                from app.models.epic_proposal import EpicProposal
                from app.models.project import Project
                from app.models.sync import SyncOutbox

                if trigger_detail == "epic_proposal:submitted":
                    proposal = (await db.execute(select(EpicProposal).where(EpicProposal.id == uuid.UUID(trigger_id)))).scalar_one_or_none()
                    if proposal:
                        context["proposal_id"] = str(proposal.id)
                        project = (await db.execute(select(Project).where(Project.id == proposal.project_id))).scalar_one_or_none()
                        if project:
                            context.update(self._project_context(project))
                    return context

                try:
                    event = (await db.execute(select(SyncOutbox).where(SyncOutbox.id == uuid.UUID(trigger_id)))).scalar_one_or_none()
                except ValueError:
                    event = None
                if event is not None:
                    context.update(
                        {
                            "event_id": str(event.id),
                            "source_system": event.system,
                            "entity_type": event.entity_type,
                            "routing_state": event.routing_state,
                            "intake_stage": (event.routing_detail or {}).get("intake_stage"),
                        }
                    )
                    if event.project_id:
                        project = (await db.execute(select(Project).where(Project.id == event.project_id))).scalar_one_or_none()
                        if project:
                            context.update(self._project_context(project))
                return context

            if trigger_detail == "project:created":
                from sqlalchemy import select

                from app.models.project import Project

                project = (await db.execute(select(Project).where(Project.id == uuid.UUID(trigger_id)))).scalar_one_or_none()
                if project:
                    context.update(self._project_context(project))
        except Exception:
            logger.exception("Failed to resolve conductor dispatch context for %s/%s", trigger_type, trigger_id)
        return context

    @staticmethod
    def _project_context(project: Any) -> dict[str, Any]:
        return {
            "project_id": str(project.id),
            "project_slug": project.slug,
            "repo_host_path": project.repo_host_path,
            "workspace_root": project.workspace_root,
            "workspace_mode": project.workspace_mode,
            "onboarding_status": project.onboarding_status,
        }

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
        from app.services.dispatch_policy import (
            SkipReason,
            count_active_dispatches,
            get_effective_policy,
        )

        if not settings.hivemind_conductor_enabled:
            return {"status": "conductor_disabled", "byoai": True}

        # --- Load per-role dispatch policy (fail-safe: falls back to defaults) ---
        policy = await get_effective_policy(agent_role, db)

        # Hard gate: role is disabled by operator
        if not policy.enabled:
            logger.info("Conductor: policy disabled for role '%s' — skipping", agent_role)
            return {
                "status": "policy_disabled",
                "agent_role": agent_role,
                "skip_reason": SkipReason.POLICY_DISABLED,
                "byoai": True,
            }

        # If no explicit execution_mode was provided (caller passed the default),
        # the policy's preferred mode takes precedence for the fallback chain.
        # Explicit mode always wins so existing callers are unaffected.
        effective_mode = _normalize_execution_mode(execution_mode)
        if fallback_chain is None:
            # Use policy fallback_chain as base; execution_mode is kept as first entry.
            effective_chain = _normalize_fallback_chain(policy.fallback_chain, effective_mode)
        else:
            effective_chain = _normalize_fallback_chain(fallback_chain, effective_mode)

        normalized_mode = effective_mode
        normalized_chain = effective_chain

        # Use per-role cooldown (policy overrides global setting)
        cooldown_s = policy.cooldown_seconds
        ck = _cooldown_key(agent_role, trigger_id, cooldown_s)
        dispatch_context = await self._resolve_dispatch_context(
            db,
            trigger_type=trigger_type,
            trigger_id=trigger_id,
            trigger_detail=trigger_detail,
        )
        from app.services.agent_threading import AgentThreadService

        thread_service = AgentThreadService(db)
        thread_context = await thread_service.resolve_context(
            agent_role=agent_role,
            task_id=dispatch_context.get("task_id"),
            epic_id=dispatch_context.get("epic_id"),
            project_id=dispatch_context.get("project_id"),
            create_session=True,
        )

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
                result=self._append_status_history(
                    {
                        "fallback_chain": normalized_chain,
                        "dispatch_context": dispatch_context,
                        "thread_context": self._serialize_thread_context(thread_context),
                        "policy": policy.as_dict(),
                        "automation_decision": {
                            "reason": SkipReason.COOLDOWN_ACTIVE,
                            "execution_mode": normalized_mode,
                            "cooldown_seconds": cooldown_s,
                        },
                    },
                    "cooldown_skipped",
                ),
            )
            await db.commit()
            return {
                "status": "cooldown_skipped",
                "skip_reason": SkipReason.COOLDOWN_ACTIVE,
                "dispatch_id": str(dispatch.id),
                "execution_mode": normalized_mode,
                "fallback_chain": normalized_chain,
            }

        # --- Per-role parallelism gate ---
        active_count = await count_active_dispatches(agent_role, db)
        if active_count >= policy.max_parallel:
            logger.info(
                "Conductor: parallel limit for '%s' (%d/%d) — skipping",
                agent_role, active_count, policy.max_parallel,
            )
            dispatch = await self._record_dispatch(
                db,
                trigger_type,
                trigger_id,
                trigger_detail,
                agent_role,
                prompt_type,
                normalized_mode,
                ck,
                status="parallel_limit_exceeded",
                result=self._append_status_history(
                    {
                        "fallback_chain": normalized_chain,
                        "dispatch_context": dispatch_context,
                        "thread_context": self._serialize_thread_context(thread_context),
                        "policy": policy.as_dict(),
                        "automation_decision": {
                            "reason": SkipReason.PARALLEL_LIMIT_EXCEEDED,
                            "execution_mode": normalized_mode,
                            "active_dispatches": active_count,
                            "max_parallel": policy.max_parallel,
                        },
                    },
                    "parallel_limit_exceeded",
                ),
            )
            await db.commit()
            return {
                "status": "parallel_limit_exceeded",
                "skip_reason": SkipReason.PARALLEL_LIMIT_EXCEEDED,
                "dispatch_id": str(dispatch.id),
                "execution_mode": normalized_mode,
                "fallback_chain": normalized_chain,
                "active_dispatches": active_count,
                "max_parallel": policy.max_parallel,
            }

        governance_payload = await self._resolve_governance_payload(db, prompt_type)
        initial_result: dict[str, Any] = self._append_status_history(
            self._append_status_history(
                {
                    "fallback_chain": normalized_chain,
                    "dispatch_context": dispatch_context,
                    "thread_context": self._serialize_thread_context(thread_context),
                    "policy": policy.as_dict(),
                    "automation_decision": {
                        "reason": trigger_detail,
                        "execution_mode": normalized_mode,
                    },
                },
                "queued",
                {"execution_mode": normalized_mode},
            ),
            "dispatched",
            {"execution_mode": normalized_mode},
        )
        if governance_payload:
            initial_result["governance"] = {
                "governance_type": governance_payload["governance_type"],
                "target_type": governance_payload["target_type"],
                "level": governance_payload["level"],
                "decisive_tools": sorted(governance_payload["decisive_tools"]),
            }
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
                        trigger_type=trigger_type,
                        agent_role=agent_role,
                        prompt_type=prompt_type,
                        thread_context=thread_context,
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
                    await thread_service.record_dispatch_outcome(
                        thread_context=thread_context,
                        dispatch_id=str(dispatch.id),
                        prompt_type=prompt_type,
                        trigger_detail=trigger_detail,
                        status="ide_dispatched",
                    )
                    await db.commit()
                    event_bus.publish("conductor:dispatch", event_payload, channel="tasks")
                    logger.info("Conductor: IDE dispatch queued via SSE for %s/%s", agent_role, trigger_id)
                    return {
                        "status": "ide_dispatched",
                        "dispatch_id": str(dispatch.id),
                        "execution_mode": normalized_mode,
                        "fallback_chain": normalized_chain,
                    }

                if normalized_mode == "byoai":
                    result_payload = self._merge_result(dispatch.result, {"byoai": True})
                    await self._update_dispatch(
                        db,
                        dispatch,
                        status="byoai",
                        result=result_payload,
                        mark_completed=True,
                    )
                    await thread_service.record_dispatch_outcome(
                        thread_context=thread_context,
                        dispatch_id=str(dispatch.id),
                        prompt_type=prompt_type,
                        trigger_detail=trigger_detail,
                        status="byoai",
                    )
                    await db.commit()
                    return {
                        "status": "byoai",
                        "dispatch_id": str(dispatch.id),
                        "execution_mode": normalized_mode,
                        "fallback_chain": normalized_chain,
                    }

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
                    await thread_service.record_dispatch_outcome(
                        thread_context=thread_context,
                        dispatch_id=str(dispatch.id),
                        prompt_type=prompt_type,
                        trigger_detail=trigger_detail,
                        status=final_status,
                        content=ga_result.get("message") if isinstance(ga_result, dict) else None,
                    )
                    await db.commit()
                    return {
                        "status": final_status,
                        "dispatch_id": str(dispatch.id),
                        "execution_mode": normalized_mode,
                        "fallback_chain": normalized_chain,
                        **ga_result,
                    }

                from app.services.agentic_dispatch import agentic_dispatch
                from app.services.agentic_dispatch import get_allowed_tool_names_for_role
                from app.services.ai_provider import NeedsManualMode, get_provider
                from app.services.learning_artifacts import capture_dispatch_learning

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
                            {
                                "byoai": True,
                                "reason": "no_provider_configured",
                                "skip_reason": SkipReason.PROVIDER_UNAVAILABLE,
                            },
                        ),
                        mark_completed=True,
                    )
                    await thread_service.record_dispatch_outcome(
                        thread_context=thread_context,
                        dispatch_id=str(dispatch.id),
                        prompt_type=prompt_type,
                        trigger_detail=trigger_detail,
                        status="byoai",
                    )
                    await db.commit()
                    logger.info("Conductor: no provider for %s → BYOAI", agent_role)
                    return {
                        "status": "byoai",
                        "skip_reason": SkipReason.PROVIDER_UNAVAILABLE,
                        "dispatch_id": str(dispatch.id),
                        "execution_mode": normalized_mode,
                        "fallback_chain": normalized_chain,
                    }

                prompt = await self._build_prompt(
                    db,
                    trigger_id=trigger_id,
                    trigger_detail=trigger_detail,
                    trigger_type=trigger_type,
                    agent_role=agent_role,
                    prompt_type=prompt_type,
                    thread_context=thread_context,
                )
                prompt_kwargs = _prompt_context_for_dispatch(
                    trigger_type=trigger_type,
                    trigger_id=trigger_id,
                    trigger_detail=trigger_detail,
                    agent_role=agent_role,
                    prompt_type=prompt_type,
                )
                allowed_tool_names: set[str] | None = None
                if governance_payload and governance_payload.get("level") == "assisted":
                    allowed_tool_names = (
                        get_allowed_tool_names_for_role(agent_role)
                        - set(governance_payload["decisive_tools"])
                    )
                try:
                    response = await agentic_dispatch(
                        provider=provider,
                        prompt=prompt,
                        agent_role=agent_role,
                        task_key=prompt_kwargs.get("task_id"),
                        epic_id=prompt_kwargs.get("epic_id"),
                        allowed_tool_names=allowed_tool_names,
                        token_budget=policy.token_budget,
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
                        await thread_service.record_dispatch_outcome(
                            thread_context=thread_context,
                            dispatch_id=str(dispatch.id),
                            prompt_type=prompt_type,
                            trigger_detail=trigger_detail,
                            status="byoai",
                            content=str(exc),
                        )
                        await db.commit()
                        return {
                            "status": "byoai",
                            "skip_reason": SkipReason.LOCAL_ERROR_FALLBACK,
                            "dispatch_id": str(dispatch.id),
                            "execution_mode": normalized_mode,
                            "fallback_chain": normalized_chain,
                        }
                    raise

                final_status = "completed" if not response.error else "partial"
                result_payload = {
                    "content": response.content,
                    "tool_calls": response.tool_calls_executed,
                    "iterations": response.iterations,
                    "input_tokens": response.total_input_tokens,
                    "output_tokens": response.total_output_tokens,
                    "model": response.model,
                    "finish_reason": response.finish_reason,
                    "error": response.error,
                }
                combined_payload = self._merge_result(dispatch.result, result_payload)
                combined_payload = await self._apply_governance_outcome(
                    db,
                    dispatch=dispatch,
                    prompt_type=prompt_type,
                    trigger_id=trigger_id,
                    agent_role=agent_role,
                    result_payload=combined_payload,
                )
                await capture_dispatch_learning(
                    db,
                    dispatch_id=str(dispatch.id),
                    agent_role=agent_role,
                    dispatch_context=dispatch_context,
                    content=response.content,
                    tool_calls=response.tool_calls_executed,
                    status=final_status,
                )
                await thread_service.record_dispatch_outcome(
                    thread_context=thread_context,
                    dispatch_id=str(dispatch.id),
                    prompt_type=prompt_type,
                    trigger_detail=trigger_detail,
                    status=final_status,
                    content=response.content,
                    model=response.model,
                    tool_calls=response.tool_calls_executed,
                )
                await self._update_dispatch(
                    db,
                    dispatch,
                    status=final_status,
                    result=combined_payload,
                    mark_completed=True,
                )
                await db.commit()
                logger.info(
                    "Conductor: dispatched %s/%s → %s tokens",
                    agent_role,
                    prompt_type,
                    response.total_output_tokens,
                )
                return {
                    "status": final_status,
                    "dispatch_id": str(dispatch.id),
                    "execution_mode": normalized_mode,
                    "fallback_chain": normalized_chain,
                    "thread_context": self._serialize_thread_context(thread_context),
                    **result_payload,
                }

            except Exception as exc:
                await thread_service.record_dispatch_outcome(
                    thread_context=thread_context,
                    dispatch_id=str(dispatch.id),
                    prompt_type=prompt_type,
                    trigger_detail=trigger_detail,
                    status="failed",
                    content=str(exc),
                )
                await self._update_dispatch(
                    db,
                    dispatch,
                    status="failed",
                    result=self._merge_result(dispatch.result, {"error": str(exc)}),
                    mark_completed=True,
                )
                await db.commit()
                logger.error("Conductor dispatch failed for %s/%s: %s", agent_role, trigger_id, exc)
                return {
                    "status": "failed",
                    "dispatch_id": str(dispatch.id),
                    "execution_mode": normalized_mode,
                    "fallback_chain": normalized_chain,
                    "thread_context": self._serialize_thread_context(thread_context),
                    "error": str(exc),
                }

    @staticmethod
    def _serialize_thread_context(thread_context: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(thread_context, dict):
            return {}
        return {
            "policy": thread_context.get("policy"),
            "configured_policy": thread_context.get("configured_policy"),
            "project_override_policy": thread_context.get("project_override_policy"),
            "thread_key": thread_context.get("thread_key"),
            "scope": thread_context.get("scope"),
            "reuse_enabled": thread_context.get("reuse_enabled"),
            "session_id": thread_context.get("session_id"),
        }

    async def on_task_state_change(
        self, task_key: str, task_id: str, old_state: str, new_state: str, db: Any
    ) -> None:
        """React to task state transitions (Rules 1-4)."""
        from app.services.governance import get_governance_level

        del task_id

        if old_state in {"scoped", "ready", "qa_failed"} and new_state == "in_progress":
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

        elif new_state == "qa_failed":
            mode, chain = await self._resolve_rule_dispatch_config(db, "task_qa_failed")
            await self.dispatch(
                trigger_type="task_state",
                trigger_id=task_key,
                trigger_detail=f"state:{old_state}->{new_state}",
                agent_role="gaertner",
                prompt_type="gaertner_review_feedback",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

        elif new_state == "escalated":
            level = await get_governance_level(db, "escalation")
            if level != "manual":
                mode, chain = await self._resolve_rule_dispatch_config(db, "task_escalated")
                await self.dispatch(
                    trigger_type="task_state",
                    trigger_id=task_key,
                    trigger_detail=f"state:{old_state}->{new_state}",
                    agent_role="triage",
                    prompt_type="triage_escalation",
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
        from sqlalchemy import select

        from app.models.sync import SyncOutbox

        try:
            event_uuid = uuid.UUID(event_id)
        except ValueError:
            return

        entry = (await db.execute(select(SyncOutbox).where(SyncOutbox.id == event_uuid))).scalar_one_or_none()
        if entry is None:
            return

        detail = dict(entry.routing_detail or {})
        if detail.get("intake_stage") != "triage_pending":
            return
        if detail.get("dispatch_status") in {
            "cooldown_skipped",
            "ide_dispatched",
            "dispatched",
            "acknowledged",
            "running",
            "completed",
            "partial",
            "byoai",
        }:
            return

        mode, chain = await self._resolve_rule_dispatch_config(db, "event_unrouted_inbound")
        dispatch_result = await self.dispatch(
            trigger_type="event",
            trigger_id=event_id,
            trigger_detail=f"event_type:{event_type}",
            agent_role="triage",
            prompt_type="triage_classify",
            db=db,
            execution_mode=mode,
            fallback_chain=chain,
        )
        detail.update(
            {
                "dispatch_status": dispatch_result.get("status"),
                "dispatch_id": dispatch_result.get("dispatch_id"),
                "dispatch_mode": dispatch_result.get("execution_mode"),
                "automation_reason": f"triage_pending:{event_type}",
            }
        )
        entry.routing_detail = detail
        await db.flush()
        await db.commit()

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
                prompt_type="triage_epic_proposal",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

    async def on_skill_proposal(self, skill_id: str, db: Any) -> None:
        """Rule 9: Skill proposal -> Triage review (if skill_merge!=manual)."""
        from app.services.governance import get_governance_level

        level = await get_governance_level(db, "skill_merge")
        if level != "manual":
            mode, chain = await self._resolve_rule_dispatch_config(db, "skill_proposal")
            await self.dispatch(
                trigger_type="event",
                trigger_id=skill_id,
                trigger_detail="skill:proposal",
                agent_role="triage",
                prompt_type="triage_skill_proposal",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

    async def on_guard_proposal(self, guard_id: str, db: Any) -> None:
        """Rule 9b: Guard proposal -> Triage review (if guard_merge!=manual)."""
        from app.services.governance import get_governance_level

        level = await get_governance_level(db, "guard_merge")
        if level != "manual":
            mode, chain = await self._resolve_rule_dispatch_config(db, "guard_proposal")
            await self.dispatch(
                trigger_type="event",
                trigger_id=guard_id,
                trigger_detail="guard:proposal",
                agent_role="triage",
                prompt_type="triage_guard_proposal",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )

    async def on_epic_restructure_proposed(self, decision_id: str, db: Any) -> None:
        """Rule 9c: Epic restructure proposal -> Triage review."""
        mode, chain = await self._resolve_rule_dispatch_config(db, "epic_restructure_proposed")
        await self.dispatch(
            trigger_type="event",
            trigger_id=decision_id,
            trigger_detail="epic_restructure:proposed",
            agent_role="triage",
            prompt_type="triage_epic_restructure",
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
        """Rule 12: Decision request -> Triage resolver (if decision_request!=manual)."""
        from app.services.governance import get_governance_level

        level = await get_governance_level(db, "decision_request")
        if level != "manual":
            mode, chain = await self._resolve_rule_dispatch_config(db, "decision_request_open")
            await self.dispatch(
                trigger_type="event",
                trigger_id=decision_id,
                trigger_detail="decision_request:open",
                agent_role="triage",
                prompt_type="triage_decision_request",
                db=db,
                execution_mode=mode,
                fallback_chain=chain,
            )


conductor = ConductorService()


# ---------------------------------------------------------------------------
# Public query helpers (used by routers — keep models out of routers)
# ---------------------------------------------------------------------------


async def get_dispatches(
    db: Any,
    *,
    limit: int = 50,
    status_filter: str | None = None,
) -> list:
    """Return dispatches ordered by dispatched_at desc."""
    from sqlalchemy import desc, select

    from app.models.conductor import ConductorDispatch

    query = (
        select(ConductorDispatch)
        .order_by(desc(ConductorDispatch.dispatched_at))
        .limit(limit)
    )
    if status_filter:
        query = query.where(ConductorDispatch.status == status_filter)
    result = await db.execute(query)
    return result.scalars().all()


async def get_pending_ide_dispatches_from_db(db: Any, *, limit: int = 50) -> list:
    """Return open IDE dispatches (dispatched/acknowledged/running), newest first."""
    from sqlalchemy import desc, select

    from app.models.conductor import ConductorDispatch

    result = await db.execute(
        select(ConductorDispatch)
        .where(
            ConductorDispatch.execution_mode == "ide",
            ConductorDispatch.status.in_(["dispatched", "acknowledged", "running"]),
        )
        .order_by(desc(ConductorDispatch.dispatched_at))
        .limit(limit)
    )
    return result.scalars().all()


async def get_dispatch_by_id(db: Any, dispatch_id: uuid.UUID) -> Any:
    """Return a single ConductorDispatch by primary-key UUID, or None."""
    from sqlalchemy import select

    from app.models.conductor import ConductorDispatch

    row = await db.execute(
        select(ConductorDispatch).where(ConductorDispatch.id == dispatch_id)
    )
    return row.scalar_one_or_none()


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
            ).limit(20)
        )
        entries = result.scalars().all()
        for entry in entries:
            detail = dict(entry.routing_detail or {})
            if detail.get("intake_stage") != "triage_pending":
                continue
            try:
                await conductor.on_inbound_event(
                    event_id=str(entry.id),
                    event_type=entry.entity_type or "unknown",
                    db=db,
                )
            except Exception as exc:
                logger.error("Conductor poll error for entry %s: %s", entry.id, exc)
