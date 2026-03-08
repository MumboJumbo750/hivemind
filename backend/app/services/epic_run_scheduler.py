from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AsyncSessionLocal
from app.models.epic import Epic
from app.models.epic_run import EpicRun
from app.models.settings import AppSettings
from app.schemas.task import TaskStateTransition
from app.services.epic_run_service import EpicRunService, TERMINAL_TASK_STATES
from app.services.task_service import TaskService

logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = {"started", "running", "waiting", "blocked"}
WORKER_SLOT_ACTIVE_STATES = {"in_progress"}


class EpicRunSchedulerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.run_service = EpicRunService(db)

    async def schedule_run(self, run_id: uuid.UUID) -> dict[str, Any]:
        run = await self._get_run(run_id)
        if run.dry_run:
            return {"status": "dry_run", "run_id": str(run.id), "dispatched_task_keys": []}

        from app.services.epic_run_context import EpicRunContextService

        epic = await self._get_epic(run.epic_id)
        project = await self.run_service._load_project(epic.project_id) if epic.project_id else None
        context_service = EpicRunContextService(self.db)
        await context_service.ensure_epic_scratchpad(run.id)
        await context_service.sync_file_claims(run.id)
        requested_parallelism = self._requested_parallelism(run)
        effective_limits = await self._resolve_effective_limits(project, requested_parallelism)
        analysis, tasks = await self._build_run_analysis(
            epic=epic,
            project=project,
            run=run,
            max_parallel_workers=effective_limits["effective_max_parallel_workers"],
        )

        execution_analysis = analysis["execution_analysis"]
        dispatch_now = list(execution_analysis["slot_plan"]["dispatch_now"])
        dispatched_task_keys = await self._dispatch_task_batch(
            run=run,
            dispatch_task_keys=dispatch_now,
        )
        available_after_dispatch = max(
            0,
            int(execution_analysis["slot_plan"]["available_slots_now"]) - len(dispatched_task_keys),
        )
        resumed_task_keys = await self._resume_task_batch(
            run=run,
            tasks=tasks,
            max_resumes=available_after_dispatch,
            context_service=context_service,
        )
        if dispatched_task_keys:
            task_by_key = {task.task_key: task for task in tasks}
            execution_mode = str(dict(run.config or {}).get("resolved_execution_mode") or "local")
            for task_key in dispatched_task_keys:
                task = task_by_key.get(task_key)
                if task is None:
                    continue
                await context_service.create_worker_handoff(
                    run.id,
                    task,
                    execution_mode=execution_mode,
                    trigger_detail="epic_run_scheduler:ready->in_progress",
                )
        await context_service.sync_file_claims(run.id)

        refreshed_analysis, refreshed_tasks = await self._build_run_analysis(
            epic=epic,
            project=project,
            run=run,
            max_parallel_workers=effective_limits["effective_max_parallel_workers"],
        )
        run.analysis = {
            **analysis,
            **{
                "execution_analysis": refreshed_analysis["execution_analysis"],
                "scheduler": {
                    "requested_max_parallel_workers": requested_parallelism,
                    **effective_limits,
                    "auto_resume_on_qa_failed": bool(
                        dict(run.config or {}).get("auto_resume_on_qa_failed", False)
                    ),
                    "dispatched_task_keys": dispatched_task_keys,
                    "resumed_task_keys": resumed_task_keys,
                    "scheduled_at": datetime.now(UTC).isoformat(),
                },
            },
        }

        run.status = self._resolve_run_status(
            tasks=refreshed_tasks,
            execution_analysis=refreshed_analysis["execution_analysis"],
            dispatched_task_keys=dispatched_task_keys,
        )
        if run.status == "completed":
            run.completed_at = datetime.now(UTC)
        else:
            run.completed_at = None

        await self.db.flush()
        return {
            "run_id": str(run.id),
            "status": run.status,
            "dispatched_task_keys": dispatched_task_keys,
            "resumed_task_keys": resumed_task_keys,
            "effective_max_parallel_workers": effective_limits["effective_max_parallel_workers"],
        }

    async def schedule_active_runs(self) -> int:
        result = await self.db.execute(
            select(EpicRun).where(
                EpicRun.dry_run.is_(False),
                EpicRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        )
        runs = list(result.scalars().all())
        processed = 0
        for run in runs:
            try:
                await self.schedule_run(run.id)
                processed += 1
            except Exception:
                logger.exception("Epic run scheduling failed for run %s", run.id)
        return processed

    async def _get_run(self, run_id: uuid.UUID) -> EpicRun:
        result = await self.db.execute(select(EpicRun).where(EpicRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise ValueError(f"EpicRun '{run_id}' nicht gefunden.")
        return run

    async def _get_epic(self, epic_id: uuid.UUID) -> Epic:
        result = await self.db.execute(select(Epic).where(Epic.id == epic_id))
        epic = result.scalar_one_or_none()
        if epic is None:
            raise ValueError(f"Epic '{epic_id}' nicht gefunden.")
        return epic

    async def _build_run_analysis(
        self,
        *,
        epic: Epic,
        project: Any,
        run: EpicRun,
        max_parallel_workers: int,
    ) -> tuple[dict[str, Any], list[Any]]:
        tasks = await self.run_service._load_tasks(epic.id)
        open_decisions = await self.run_service._load_open_decisions(
            epic.id,
            [task.id for task in tasks if getattr(task, "id", None) is not None],
        )
        active_dispatches = await self.run_service._load_active_task_dispatches(
            [task.task_key for task in tasks]
        )
        governance = await self._load_governance()
        dispatch_info = {
            "requested_mode": dict(run.config or {}).get("execution_mode_preference"),
            "resolved_mode": dict(run.config or {}).get("resolved_execution_mode", "local"),
            "available": True,
            "reason": "epic_run_scheduler",
        }
        analysis = self.run_service._build_analysis(
            project=project,
            tasks=tasks,
            governance=governance,
            dispatch_info=dispatch_info,
            open_decisions=open_decisions,
            active_dispatches=active_dispatches,
            max_parallel_workers=max_parallel_workers,
            respect_file_claims=bool(dict(run.config or {}).get("respect_file_claims", True)),
        )
        return analysis, tasks

    async def _load_governance(self) -> dict[str, Any]:
        from app.services.governance import get_governance

        return await get_governance(self.db)

    async def _dispatch_task_batch(
        self,
        *,
        run: EpicRun,
        dispatch_task_keys: list[str],
    ) -> list[str]:
        if not dispatch_task_keys:
            return []

        from app.services.conductor import conductor

        dispatched: list[str] = []
        task_service = TaskService(self.db)
        execution_mode = str(dict(run.config or {}).get("resolved_execution_mode") or "local")

        for task_key in dispatch_task_keys:
            task = await task_service.transition_state(
                task_key,
                TaskStateTransition(state="in_progress"),
                skip_conductor=True,
            )
            await conductor.dispatch(
                trigger_type="task_state",
                trigger_id=task.task_key,
                trigger_detail="epic_run_scheduler:ready->in_progress",
                agent_role="worker",
                prompt_type="agentic_worker",
                db=self.db,
                execution_mode=execution_mode,
                source_dispatch_id=str(run.id),
            )
            dispatched.append(task.task_key)

        return dispatched

    async def _resume_task_batch(
        self,
        *,
        run: EpicRun,
        tasks: list[Any],
        max_resumes: int,
        context_service: Any,
    ) -> list[str]:
        if max_resumes < 1:
            return []
        if not bool(dict(run.config or {}).get("auto_resume_on_qa_failed", False)):
            return []

        execution_mode = str(dict(run.config or {}).get("resolved_execution_mode") or "local")
        resume_candidates = [
            task
            for task in tasks
            if task.state == "qa_failed" and (task.qa_failed_count or 0) < 3
        ]
        if not resume_candidates:
            return []

        from app.services.conductor import conductor

        task_service = TaskService(self.db)
        resumed: list[str] = []
        for task in resume_candidates[:max_resumes]:
            resume_package = await context_service.get_latest_resume_package(task)
            if resume_package is None:
                continue
            updated_task = await task_service.reenter_from_qa_failed(
                task.task_key,
                skip_conductor=True,
            )
            await context_service.create_worker_handoff(
                run.id,
                updated_task,
                execution_mode=execution_mode,
                trigger_detail="epic_run_scheduler:qa_failed->in_progress",
                summary_suffix="Basis ist das aktuelle Resume-Paket.",
            )
            await conductor.dispatch(
                trigger_type="task_state",
                trigger_id=updated_task.task_key,
                trigger_detail="epic_run_scheduler:qa_failed->in_progress",
                agent_role="worker",
                prompt_type="agentic_worker",
                db=self.db,
                execution_mode=execution_mode,
                source_dispatch_id=str(run.id),
            )
            resumed.append(updated_task.task_key)
        return resumed

    async def _resolve_effective_limits(
        self,
        project: Any,
        requested_parallelism: int,
    ) -> dict[str, Any]:
        policy = await self._load_scheduler_policy()
        role_limit = self._normalize_limit_value((policy.get("role_limits") or {}).get("worker"))
        global_limit = self._normalize_limit_value(policy.get("global_max_parallel_workers"))

        project_limits = policy.get("project_limits") or {}
        project_limit = None
        if project is not None:
            project_limit = self._resolve_project_limit(project_limits, project)

        candidates = [requested_parallelism, settings.hivemind_conductor_parallel]
        if global_limit:
            candidates.append(global_limit)
        if role_limit:
            candidates.append(role_limit)
        if project_limit:
            candidates.append(project_limit)

        effective = max(1, min(value for value in candidates if value and value > 0))
        return {
            "global_max_parallel_workers": global_limit,
            "project_max_parallel_workers": project_limit,
            "role_max_parallel_workers": role_limit,
            "conductor_parallel_limit": settings.hivemind_conductor_parallel,
            "effective_max_parallel_workers": effective,
        }

    async def _load_scheduler_policy(self) -> dict[str, Any]:
        result = await self.db.execute(
            select(AppSettings).where(AppSettings.key == "epic_run_scheduler_limits")
        )
        row = result.scalar_one_or_none()
        if row is None or not row.value:
            return {}

        try:
            parsed = json.loads(row.value) if isinstance(row.value, str) else row.value
        except Exception:
            logger.warning("Invalid epic_run_scheduler_limits JSON, ignoring")
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _resolve_project_limit(project_limits: dict[str, Any], project: Any) -> int | None:
        project_keys = {
            str(getattr(project, "id", "")),
            str(getattr(project, "slug", "")),
        }
        for project_key in project_keys:
            if not project_key:
                continue
            raw = project_limits.get(project_key)
            if raw is None:
                continue
            if isinstance(raw, dict):
                return EpicRunSchedulerService._normalize_limit_value(
                    raw.get("max_parallel_workers") or raw.get("worker")
                )
            return EpicRunSchedulerService._normalize_limit_value(raw)
        return None

    @staticmethod
    def _normalize_limit_value(raw: Any) -> int | None:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _requested_parallelism(run: EpicRun) -> int:
        config = dict(run.config or {})
        try:
            requested = int(config.get("max_parallel_workers") or 1)
        except (TypeError, ValueError):
            requested = 1
        return max(requested, 1)

    @staticmethod
    def _resolve_run_status(
        *,
        tasks: list[Any],
        execution_analysis: dict[str, Any],
        dispatched_task_keys: list[str],
    ) -> str:
        if tasks and all(task.state in TERMINAL_TASK_STATES for task in tasks):
            return "completed"

        if dispatched_task_keys:
            return "running"

        active_worker_tasks = [
            task for task in tasks if task.state in WORKER_SLOT_ACTIVE_STATES
        ]
        if active_worker_tasks:
            return "running"

        slot_plan = execution_analysis.get("slot_plan") or {}
        if slot_plan.get("dispatch_now") or slot_plan.get("queued_runnable"):
            return "waiting"

        waiting = (execution_analysis.get("waiting") or [])
        conflicting = (execution_analysis.get("conflicting") or [])
        blocked = (execution_analysis.get("blocked") or [])
        if waiting or conflicting:
            return "waiting"
        if blocked:
            return "blocked"
        return "waiting"


async def epic_run_scheduler_job() -> None:
    async with AsyncSessionLocal() as db:
        processed = await EpicRunSchedulerService(db).schedule_active_runs()
        if processed:
            logger.info("Epic run scheduler processed %d run(s)", processed)
        await db.commit()
