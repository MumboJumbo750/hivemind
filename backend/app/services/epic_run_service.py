from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conductor import ConductorDispatch
from app.models.decision import DecisionRequest
from app.models.epic_run import EpicRun
from app.models.project import Project
from app.models.task import Task
from app.schemas.auth import CurrentActor
from app.schemas.epic import EpicStartBlocker, EpicStartRequest, EpicStartResponse
from app.services.ai_provider import NeedsManualMode, get_provider
from app.services.epic_service import EpicService
from app.services.governance import get_governance


TERMINAL_TASK_STATES = {"done", "cancelled"}
ACTIVE_TASK_STATES = {"in_progress", "in_review"}
STARTABLE_EPIC_STATES = {"scoped", "in_progress"}
WAITING_TASK_STATES = {"incoming", "scoped"}
BLOCKED_TASK_STATES = {"blocked", "escalated", "qa_failed"}
RUNNABLE_TASK_STATES = {"ready"}
ACTIVE_DISPATCH_STATUSES = {"dispatched", "acknowledged", "running"}
FILE_CLAIM_KINDS = {"file_claim", "file-claim", "claim"}
READ_ONLY_CLAIM_MODES = {"shared-read", "shared_read", "read"}
DEPENDENCY_FIELDS = {
    "depends_on",
    "dependency_task_keys",
    "blocked_by",
    "requires_tasks",
    "predecessors",
    "dependencies",
}
CONTEXT_RELATION_FIELDS = {
    "related_tasks",
    "task_refs",
    "context_task_keys",
    "handoff_from",
    "handoff_to",
}


def _reason(code: str, message: str, **extra: Any) -> dict[str, Any]:
    payload = {"code": code, "message": message}
    payload.update({key: value for key, value in extra.items() if value not in (None, [], {}, "")})
    return payload


def _normalize_claim_mode(raw: Any) -> str:
    value = str(raw or "exclusive").strip().lower().replace("_", "-")
    return value or "exclusive"


def _normalize_claim_path(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().replace("\\", "/").rstrip("/")
    if not value:
        return None
    return value.casefold()


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _extract_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        values: list[str] = []
        for item in value:
            values.extend(_extract_values(item))
        return values
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(_extract_values(item))
        return values
    return [str(value)]


@lru_cache(maxsize=8)
def _load_seed_task_dependency_map(workspace_root: str | None) -> dict[str, list[str]]:
    if not workspace_root:
        return {}

    tasks_dir = Path(workspace_root) / "seed" / "tasks"
    if not tasks_dir.exists():
        return {}

    mapping: dict[str, list[str]] = {}
    for seed_file in tasks_dir.rglob("*.json"):
        try:
            data = json.loads(seed_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        external_id = str(data.get("external_id") or "").strip()
        if not external_id:
            continue
        depends_on = [str(item).strip() for item in (data.get("depends_on") or []) if str(item).strip()]
        mapping[external_id] = depends_on
    return mapping


class EpicRunService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_runs(
        self,
        epic_key: str,
        actor: CurrentActor,
        *,
        limit: int = 10,
    ) -> list[EpicRun]:
        epic = await EpicService(self.db).get_by_key(epic_key)
        self._ensure_access(epic.owner_id, epic.backup_owner_id, actor)
        result = await self.db.execute(
            select(EpicRun)
            .where(EpicRun.epic_id == epic.id)
            .order_by(EpicRun.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_run(
        self,
        run_id: uuid.UUID,
        actor: CurrentActor,
    ) -> EpicRun:
        result = await self.db.execute(select(EpicRun).where(EpicRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"EpicRun '{run_id}' nicht gefunden.",
            )

        epic = await EpicService(self.db).get_by_id_or_none(run.epic_id)
        if epic is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Epic fuer Run '{run_id}' nicht gefunden.",
            )
        self._ensure_access(epic.owner_id, epic.backup_owner_id, actor)
        return run

    async def start(
        self,
        epic_key: str,
        body: EpicStartRequest,
        actor: CurrentActor,
    ) -> EpicStartResponse:
        epic = await EpicService(self.db).get_by_key(epic_key)
        self._ensure_access(epic.owner_id, epic.backup_owner_id, actor)

        project = await self._load_project(epic.project_id) if epic.project_id else None
        tasks = await self._load_tasks(epic.id)
        open_decisions = await self._load_open_decisions(
            epic.id,
            [task.id for task in tasks if getattr(task, "id", None) is not None],
        )
        active_dispatches = await self._load_active_task_dispatches([task.task_key for task in tasks])
        governance = await get_governance(self.db)
        dispatch_info = await self._resolve_worker_dispatch_mode(
            body.execution_mode_preference
        )
        blockers = self._collect_blockers(
            epic_state=epic.state,
            project=project,
            tasks=tasks,
            dispatch_info=dispatch_info,
            max_parallel_workers=body.max_parallel_workers,
        )
        startable = not blockers

        config = {
            "max_parallel_workers": body.max_parallel_workers,
            "execution_mode_preference": body.execution_mode_preference,
            "resolved_execution_mode": dispatch_info["resolved_mode"],
            "respect_file_claims": body.respect_file_claims,
            "auto_resume_on_qa_failed": body.auto_resume_on_qa_failed,
        }
        analysis = self._build_analysis(
            project=project,
            tasks=tasks,
            governance=governance,
            dispatch_info=dispatch_info,
            open_decisions=open_decisions,
            active_dispatches=active_dispatches,
            max_parallel_workers=body.max_parallel_workers,
            respect_file_claims=body.respect_file_claims,
        )

        run_status = self._resolve_run_status(dry_run=body.dry_run, startable=startable)
        run = EpicRun(
            id=uuid.uuid4(),
            epic_id=epic.id,
            started_by=actor.id,
            status=run_status,
            dry_run=body.dry_run,
            config=config,
            analysis={**analysis, "blockers": [b.model_dump() for b in blockers]},
            completed_at=datetime.now(UTC) if run_status in {"dry_run", "blocked"} else None,
        )
        self.db.add(run)

        if startable and not body.dry_run and epic.state == "scoped":
            epic.state = "in_progress"
            epic.version += 1

        await self.db.flush()
        await self.db.refresh(run)

        if startable and not body.dry_run:
            from app.services.epic_run_context import EpicRunContextService
            from app.services.epic_run_scheduler import EpicRunSchedulerService

            await EpicRunContextService(self.db).ensure_epic_scratchpad(run.id)
            schedule_result = await EpicRunSchedulerService(self.db).schedule_run(run.id)
            run.status = str(schedule_result["status"])
            analysis = dict(run.analysis or {})

        return EpicStartResponse(
            run_id=run.id,
            epic_key=epic.epic_key,
            status=run.status,
            dry_run=run.dry_run,
            startable=startable,
            epic_state=epic.state,
            config=config,
            blockers=blockers,
            analysis=analysis,
        )

    @staticmethod
    def _ensure_access(
        owner_id: uuid.UUID | None,
        backup_owner_id: uuid.UUID | None,
        actor: CurrentActor,
    ) -> None:
        if actor.role == "admin":
            return
        if actor.id in {owner_id, backup_owner_id}:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Epic-Owner, Backup-Owner oder Admin duerfen Epic Runs starten.",
        )

    async def _load_project(self, project_id: uuid.UUID) -> Project | None:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        return result.scalar_one_or_none()

    async def _load_tasks(self, epic_id: uuid.UUID) -> list[Task]:
        result = await self.db.execute(
            select(Task).where(Task.epic_id == epic_id).order_by(Task.created_at.asc())
        )
        return list(result.scalars().all())

    async def _load_open_decisions(
        self,
        epic_id: uuid.UUID,
        task_ids: list[uuid.UUID],
    ) -> list[DecisionRequest]:
        conditions = [DecisionRequest.epic_id == epic_id]
        if task_ids:
            conditions.append(DecisionRequest.task_id.in_(task_ids))

        result = await self.db.execute(
            select(DecisionRequest).where(
                DecisionRequest.state == "open",
                or_(*conditions),
            )
        )
        return list(result.scalars().all())

    async def _load_active_task_dispatches(
        self,
        task_keys: list[str],
    ) -> list[ConductorDispatch]:
        if not task_keys:
            return []

        result = await self.db.execute(
            select(ConductorDispatch).where(
                ConductorDispatch.trigger_type == "task_state",
                ConductorDispatch.trigger_id.in_(task_keys),
                ConductorDispatch.status.in_(ACTIVE_DISPATCH_STATUSES),
            )
        )
        return list(result.scalars().all())

    async def _resolve_worker_dispatch_mode(
        self,
        preferred_mode: str | None,
    ) -> dict[str, Any]:
        requested_mode = preferred_mode or "local"
        candidate_modes = [requested_mode]
        if preferred_mode is None and requested_mode != "byoai":
            candidate_modes.append("byoai")

        for mode in candidate_modes:
            if mode in {"ide", "github_actions", "byoai"}:
                return {
                    "requested_mode": preferred_mode,
                    "resolved_mode": mode,
                    "available": True,
                    "reason": "mode_available",
                }
            if mode == "local":
                try:
                    await get_provider("worker", self.db)
                    return {
                        "requested_mode": preferred_mode,
                        "resolved_mode": "local",
                        "available": True,
                        "reason": "provider_configured",
                    }
                except NeedsManualMode:
                    continue

        return {
            "requested_mode": preferred_mode,
            "resolved_mode": requested_mode,
            "available": False,
            "reason": "Kein passender Worker-Dispatch-Modus verfuegbar.",
        }

    def _collect_blockers(
        self,
        *,
        epic_state: str,
        project: Project | None,
        tasks: list[Task],
        dispatch_info: dict[str, Any],
        max_parallel_workers: int,
    ) -> list[EpicStartBlocker]:
        blockers: list[EpicStartBlocker] = []

        if epic_state not in STARTABLE_EPIC_STATES:
            blockers.append(
                EpicStartBlocker(
                    code="EPIC_STATE_INVALID",
                    message=(
                        f"Epic muss in {sorted(STARTABLE_EPIC_STATES)} sein, ist aber '{epic_state}'."
                    ),
                )
            )

        if max_parallel_workers < 1:
            blockers.append(
                EpicStartBlocker(
                    code="INVALID_PARALLELISM",
                    message="max_parallel_workers muss mindestens 1 sein.",
                )
            )

        if project is None:
            blockers.append(
                EpicStartBlocker(
                    code="PROJECT_MISSING",
                    message="Epic ist keinem Projekt mit Workspace-Kontext zugeordnet.",
                )
            )
        else:
            if not (project.repo_host_path or "").strip():
                blockers.append(
                    EpicStartBlocker(
                        code="WORKSPACE_REPO_MISSING",
                        message="Projekt hat keinen repo_host_path konfiguriert.",
                    )
                )
            if not (project.workspace_root or "").strip():
                blockers.append(
                    EpicStartBlocker(
                        code="WORKSPACE_ROOT_MISSING",
                        message="Projekt hat keinen workspace_root konfiguriert.",
                    )
                )
            if (project.onboarding_status or "").strip().lower() == "error":
                blockers.append(
                    EpicStartBlocker(
                        code="WORKSPACE_ONBOARDING_ERROR",
                        message="Projekt-Workspace ist im Onboarding-Fehlerzustand.",
                    )
                )

        if not tasks:
            blockers.append(
                EpicStartBlocker(
                    code="TASKS_MISSING",
                    message="Epic enthaelt noch keine Tasks.",
                )
            )
        else:
            if any(not (task.title or "").strip() for task in tasks):
                blockers.append(
                    EpicStartBlocker(
                        code="TASK_INVALID_TITLE",
                        message="Mindestens eine Task hat keinen gueltigen Titel.",
                    )
                )

            if all(task.state in TERMINAL_TASK_STATES for task in tasks):
                blockers.append(
                    EpicStartBlocker(
                        code="NO_OPEN_TASKS",
                        message="Epic hat keine offenen Tasks mehr.",
                    )
                )

            active_tasks = [task.task_key for task in tasks if task.state in ACTIVE_TASK_STATES]
            if active_tasks:
                blockers.append(
                    EpicStartBlocker(
                        code="ACTIVE_TASKS_PRESENT",
                        message=(
                            "Epic hat bereits laufende Tasks: " + ", ".join(active_tasks[:5])
                        ),
                    )
                )

        if not dispatch_info["available"]:
            blockers.append(
                EpicStartBlocker(
                    code="WORKER_MODE_UNAVAILABLE",
                    message=str(dispatch_info["reason"]),
                )
            )

        return blockers

    @staticmethod
    def _resolve_run_status(*, dry_run: bool, startable: bool) -> str:
        if dry_run:
            return "dry_run"
        return "started" if startable else "blocked"

    def _build_analysis(
        self,
        *,
        project: Project | None,
        tasks: list[Task],
        governance: dict[str, str],
        dispatch_info: dict[str, Any],
        open_decisions: list[DecisionRequest],
        active_dispatches: list[ConductorDispatch],
        max_parallel_workers: int,
        respect_file_claims: bool,
    ) -> dict[str, Any]:
        state_counts: dict[str, int] = {}
        for task in tasks:
            state_counts[task.state] = state_counts.get(task.state, 0) + 1

        execution_analysis = self._build_execution_analysis(
            project=project,
            tasks=tasks,
            open_decisions=open_decisions,
            active_dispatches=active_dispatches,
            max_parallel_workers=max_parallel_workers,
            respect_file_claims=respect_file_claims,
        )

        return {
            "workspace": {
                "project_id": str(project.id) if project else None,
                "repo_host_path": getattr(project, "repo_host_path", None) if project else None,
                "workspace_root": getattr(project, "workspace_root", None) if project else None,
                "workspace_mode": getattr(project, "workspace_mode", None) if project else None,
                "onboarding_status": getattr(project, "onboarding_status", None) if project else None,
            },
            "task_summary": {
                "total": len(tasks),
                "open": len([task for task in tasks if task.state not in TERMINAL_TASK_STATES]),
                "states": state_counts,
            },
            "governance": governance,
            "worker_dispatch": dispatch_info,
            "execution_analysis": execution_analysis,
        }

    def _build_execution_analysis(
        self,
        *,
        project: Project | None,
        tasks: list[Task],
        open_decisions: list[DecisionRequest],
        active_dispatches: list[ConductorDispatch],
        max_parallel_workers: int,
        respect_file_claims: bool,
    ) -> dict[str, Any]:
        task_by_key = {task.task_key: task for task in tasks}
        task_by_id = {str(task.id): task for task in tasks if getattr(task, "id", None) is not None}
        known_task_keys = set(task_by_key)

        dependency_map, dependency_edges = self._build_dependency_map(
            project=project,
            tasks=tasks,
            known_task_keys=known_task_keys,
        )
        context_relations, context_edges = self._build_context_relations(
            tasks=tasks,
            known_task_keys=known_task_keys,
        )
        parent_children: dict[str, list[str]] = defaultdict(list)
        parent_edges: list[dict[str, Any]] = []
        for task in tasks:
            parent_id = getattr(task, "parent_task_id", None)
            if not parent_id:
                continue
            parent = task_by_id.get(str(parent_id))
            if parent is None:
                continue
            parent_children[parent.task_key].append(task.task_key)
            parent_edges.append(
                {
                    "from": parent.task_key,
                    "to": task.task_key,
                    "kind": "parent_subtask",
                    "source": "parent_task_id",
                }
            )

        task_decisions: dict[str, list[DecisionRequest]] = defaultdict(list)
        epic_decisions: list[DecisionRequest] = []
        for decision in open_decisions:
            if decision.task_id is not None:
                task = task_by_id.get(str(decision.task_id))
                if task is not None:
                    task_decisions[task.task_key].append(decision)
                    continue
            epic_decisions.append(decision)

        dispatches_by_task: dict[str, list[ConductorDispatch]] = defaultdict(list)
        for dispatch in active_dispatches:
            dispatches_by_task[str(dispatch.trigger_id)].append(dispatch)

        file_claims_by_task = {
            task.task_key: self._extract_file_claims(task)
            for task in tasks
        }
        active_claims = {
            task.task_key: file_claims_by_task[task.task_key]
            for task in tasks
            if task.state in ACTIVE_TASK_STATES and file_claims_by_task[task.task_key]
        }

        waiting: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        conflicting: list[dict[str, Any]] = []
        runnable_candidates: list[dict[str, Any]] = []
        completed: list[dict[str, Any]] = []
        task_order = {task.task_key: index for index, task in enumerate(tasks)}

        for task in tasks:
            reasons: list[dict[str, Any]] = []
            dependency_keys = dependency_map.get(task.task_key, [])
            blocking_dependencies = [
                dep_key
                for dep_key in dependency_keys
                if dep_key in task_by_key and task_by_key[dep_key].state not in TERMINAL_TASK_STATES
            ]
            open_subtasks = [
                child_key
                for child_key in parent_children.get(task.task_key, [])
                if child_key in task_by_key and task_by_key[child_key].state not in TERMINAL_TASK_STATES
            ]
            task_dispatches = dispatches_by_task.get(task.task_key, [])
            task_claims = file_claims_by_task.get(task.task_key, [])
            task_decision_ids = [str(decision.id) for decision in task_decisions.get(task.task_key, [])]
            epic_decision_ids = [str(decision.id) for decision in epic_decisions]

            base_payload = {
                "task_key": task.task_key,
                "title": task.title,
                "state": task.state,
                "depends_on": dependency_keys,
                "context_relations": context_relations.get(task.task_key, []),
                "subtasks": parent_children.get(task.task_key, []),
                "file_claims": task_claims,
                "active_dispatch_ids": [str(dispatch.id) for dispatch in task_dispatches],
                "open_decision_ids": task_decision_ids + epic_decision_ids,
            }

            if task.state in TERMINAL_TASK_STATES:
                completed.append({**base_payload, "reasons": []})
                continue

            if task.state in WAITING_TASK_STATES:
                reasons.append(
                    _reason(
                        "TASK_STATE_NOT_READY",
                        f"Task steht noch in '{task.state}' und ist damit nicht dispatchbar.",
                    )
                )
                waiting.append({**base_payload, "reasons": reasons})
                continue

            if task.state in BLOCKED_TASK_STATES:
                blocker_code = {
                    "blocked": "TASK_BLOCKED_STATE",
                    "escalated": "TASK_ESCALATED",
                    "qa_failed": "RESUME_REQUIRED",
                }.get(task.state, "TASK_NOT_RUNNABLE")
                blocker_message = {
                    "blocked": "Task ist explizit blockiert.",
                    "escalated": "Task wurde eskaliert und braucht manuellen Eingriff.",
                    "qa_failed": "Task braucht nach QA-Failure einen gezielten Resume-/Reentry-Pfad.",
                }.get(task.state, f"Task ist im Zustand '{task.state}'.")
                reasons.append(_reason(blocker_code, blocker_message))
                blocked.append({**base_payload, "reasons": reasons})
                continue

            if task.state in ACTIVE_TASK_STATES:
                reasons.append(
                    _reason(
                        "TASK_ALREADY_ACTIVE",
                        f"Task ist bereits in '{task.state}'.",
                    )
                )
                blocked.append({**base_payload, "reasons": reasons})
                continue

            if task.state not in RUNNABLE_TASK_STATES:
                reasons.append(
                    _reason(
                        "TASK_STATE_UNSUPPORTED",
                        f"Task-State '{task.state}' ist fuer den Runnable-Check aktuell nicht als Startzustand definiert.",
                    )
                )
                blocked.append({**base_payload, "reasons": reasons})
                continue

            if blocking_dependencies:
                reasons.append(
                    _reason(
                        "DEPENDENCIES_OPEN",
                        "Task wartet auf offene Vorgänger.",
                        related_task_keys=blocking_dependencies,
                    )
                )
                waiting.append({**base_payload, "reasons": reasons})
                continue

            if open_subtasks:
                reasons.append(
                    _reason(
                        "SUBTASKS_OPEN",
                        "Parent-Task wartet auf offene Subtasks.",
                        related_task_keys=open_subtasks,
                    )
                )
                waiting.append({**base_payload, "reasons": reasons})
                continue

            if task_decision_ids:
                reasons.append(
                    _reason(
                        "TASK_DECISION_OPEN",
                        "Task hat eine offene Decision Request.",
                        decision_ids=task_decision_ids,
                    )
                )
            if epic_decision_ids:
                reasons.append(
                    _reason(
                        "EPIC_DECISION_OPEN",
                        "Epic hat eine offene Decision Request, die den Start blockiert.",
                        decision_ids=epic_decision_ids,
                    )
                )
            if task_dispatches:
                reasons.append(
                    _reason(
                        "DISPATCH_ALREADY_ACTIVE",
                        "Fuer die Task laeuft bereits ein aktiver Dispatch.",
                        dispatch_ids=[str(dispatch.id) for dispatch in task_dispatches],
                    )
                )

            if reasons:
                blocked.append({**base_payload, "reasons": reasons})
                continue

            runnable_candidates.append({**base_payload, "reasons": []})

        runnable: list[dict[str, Any]] = []
        selected_claims: dict[str, list[dict[str, Any]]] = {}

        for candidate in sorted(
            runnable_candidates,
            key=lambda item: (task_order.get(str(item["task_key"]), 10_000), str(item["task_key"])),
        ):
            if not respect_file_claims or not candidate["file_claims"]:
                runnable.append(candidate)
                selected_claims[candidate["task_key"]] = candidate["file_claims"]
                continue

            conflict_reasons: list[dict[str, Any]] = []
            for other_task_key, other_claims in active_claims.items():
                claim_conflicts = self._find_file_claim_conflicts(
                    candidate["file_claims"],
                    other_claims,
                )
                if claim_conflicts:
                    conflict_reasons.append(
                        _reason(
                            "FILE_CLAIM_CONFLICT_ACTIVE",
                            "Task kollidiert mit aktiver Arbeit an denselben Dateien/Pfaden.",
                            related_task_keys=[other_task_key],
                            file_conflicts=claim_conflicts,
                        )
                    )
            for other_task_key, other_claims in selected_claims.items():
                claim_conflicts = self._find_file_claim_conflicts(
                    candidate["file_claims"],
                    other_claims,
                )
                if claim_conflicts:
                    conflict_reasons.append(
                        _reason(
                            "FILE_CLAIM_CONFLICT",
                            "Task kollidiert mit einer parallel ausgewaehlten Runnable-Task.",
                            related_task_keys=[other_task_key],
                            file_conflicts=claim_conflicts,
                        )
                    )

            if conflict_reasons:
                conflicting.append({**candidate, "reasons": conflict_reasons})
                continue

            runnable.append(candidate)
            selected_claims[candidate["task_key"]] = candidate["file_claims"]

        occupied_slots = len([task for task in tasks if task.state == "in_progress"])
        available_slots_now = max(0, max_parallel_workers - occupied_slots)

        return {
            "summary": {
                "runnable": len(runnable),
                "waiting": len(waiting),
                "blocked": len(blocked),
                "conflicting": len(conflicting),
                "completed": len(completed),
            },
            "graph": {
                "nodes": [
                    {
                        "task_key": task.task_key,
                        "state": task.state,
                        "title": task.title,
                    }
                    for task in tasks
                ],
                "edges": dependency_edges + parent_edges + context_edges,
            },
            "runnable": runnable,
            "waiting": waiting,
            "blocked": blocked,
            "conflicting": conflicting,
            "completed": completed,
            "slot_plan": {
                "max_parallel_workers": max_parallel_workers,
                "occupied_slots": occupied_slots,
                "available_slots_now": available_slots_now,
                "dispatch_now": [item["task_key"] for item in runnable[:available_slots_now]],
                "queued_runnable": [item["task_key"] for item in runnable[available_slots_now:]],
            },
        }

    def _build_dependency_map(
        self,
        *,
        project: Project | None,
        tasks: list[Task],
        known_task_keys: set[str],
    ) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
        dependency_map: dict[str, set[str]] = defaultdict(set)
        dependency_edges: list[dict[str, Any]] = []
        seed_dependency_map = _load_seed_task_dependency_map(
            project.workspace_root if project else None
        )

        for task in tasks:
            raw_dependencies: list[tuple[str, str]] = []
            raw_dependencies.extend(
                (dep_key, "seed")
                for dep_key in seed_dependency_map.get(
                    getattr(task, "external_id", None) or task.task_key,
                    [],
                )
            )
            raw_dependencies.extend(
                (dep_key, "artifact")
                for dep_key in self._extract_declared_dependency_keys(task, known_task_keys)
            )

            for dep_key, source in raw_dependencies:
                if dep_key not in known_task_keys or dep_key == task.task_key:
                    continue
                if dep_key in dependency_map[task.task_key]:
                    continue
                dependency_map[task.task_key].add(dep_key)
                dependency_edges.append(
                    {
                        "from": dep_key,
                        "to": task.task_key,
                        "kind": "depends_on",
                        "source": source,
                    }
                )

        return (
            {
                task_key: sorted(dependency_keys)
                for task_key, dependency_keys in dependency_map.items()
            },
            dependency_edges,
        )

    def _build_context_relations(
        self,
        *,
        tasks: list[Task],
        known_task_keys: set[str],
    ) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
        relations: dict[str, set[str]] = defaultdict(set)
        edges: list[dict[str, Any]] = []

        for task in tasks:
            for related_key, source in self._extract_context_relation_keys(task, known_task_keys):
                if related_key == task.task_key:
                    continue
                if related_key in relations[task.task_key]:
                    continue
                relations[task.task_key].add(related_key)
                edges.append(
                    {
                        "from": task.task_key,
                        "to": related_key,
                        "kind": "context_relation",
                        "source": source,
                    }
                )

        return (
            {task_key: sorted(related) for task_key, related in relations.items()},
            edges,
        )

    def _extract_declared_dependency_keys(
        self,
        task: Task,
        known_task_keys: set[str],
    ) -> list[str]:
        dependency_keys: set[str] = set()
        for container in (
            getattr(task, "definition_of_done", None),
            getattr(task, "quality_gate", None),
            getattr(task, "artifacts", None),
        ):
            if not isinstance(container, (dict, list)):
                continue
            dependency_keys.update(
                self._extract_keys_from_fields(container, DEPENDENCY_FIELDS, known_task_keys)
            )
        return sorted(dependency_keys)

    def _extract_context_relation_keys(
        self,
        task: Task,
        known_task_keys: set[str],
    ) -> list[tuple[str, str]]:
        relations: set[tuple[str, str]] = set()
        for container in (
            getattr(task, "definition_of_done", None),
            getattr(task, "quality_gate", None),
            getattr(task, "artifacts", None),
        ):
            if not isinstance(container, (dict, list)):
                continue
            for related_key in self._extract_keys_from_fields(
                container,
                CONTEXT_RELATION_FIELDS,
                known_task_keys,
            ):
                relations.add((related_key, "artifact"))

        for task_key in known_task_keys:
            if task_key == task.task_key:
                continue
            if task_key in str(getattr(task, "description", "") or ""):
                relations.add((task_key, "description"))

        return sorted(relations)

    def _extract_keys_from_fields(
        self,
        container: Any,
        field_names: set[str],
        known_task_keys: set[str],
    ) -> set[str]:
        found: set[str] = set()
        if isinstance(container, dict):
            for key, value in container.items():
                if key in field_names:
                    found.update(item for item in _extract_values(value) if item in known_task_keys)
                else:
                    found.update(self._extract_keys_from_fields(value, field_names, known_task_keys))
        elif isinstance(container, list):
            for item in container:
                found.update(self._extract_keys_from_fields(item, field_names, known_task_keys))
        return found

    def _extract_file_claims(self, task: Task) -> list[dict[str, Any]]:
        claims: list[dict[str, Any]] = []
        for artifact in (getattr(task, "artifacts", None) or []):
            if not isinstance(artifact, dict):
                continue
            kind = str(artifact.get("kind") or artifact.get("type") or "").strip().lower()
            if kind not in FILE_CLAIM_KINDS:
                continue

            raw_paths = []
            for field in ("path", "paths", "file", "files", "target", "targets"):
                raw_paths.extend(_extract_values(artifact.get(field)))

            normalized_paths = []
            for raw_path in raw_paths:
                normalized_path = _normalize_claim_path(raw_path)
                if normalized_path and normalized_path not in normalized_paths:
                    normalized_paths.append(normalized_path)

            if not normalized_paths:
                continue

            claims.append(
                {
                    "paths": normalized_paths,
                    "claim_type": _normalize_claim_mode(
                        artifact.get("claim_type") or artifact.get("mode")
                    ),
                }
            )
        return claims

    def _find_file_claim_conflicts(
        self,
        left_claims: list[dict[str, Any]],
        right_claims: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        for left in left_claims:
            for right in right_claims:
                left_mode = _normalize_claim_mode(left.get("claim_type"))
                right_mode = _normalize_claim_mode(right.get("claim_type"))
                if left_mode in READ_ONLY_CLAIM_MODES and right_mode in READ_ONLY_CLAIM_MODES:
                    continue

                for left_path in left.get("paths", []):
                    for right_path in right.get("paths", []):
                        if _paths_overlap(str(left_path), str(right_path)):
                            conflicts.append(
                                {
                                    "left_path": left_path,
                                    "left_claim_type": left_mode,
                                    "right_path": right_path,
                                    "right_claim_type": right_mode,
                                }
                            )
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for item in conflicts:
            key = (
                str(item["left_path"]),
                str(item["left_claim_type"]),
                str(item["right_path"]),
                str(item["right_claim_type"]),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
