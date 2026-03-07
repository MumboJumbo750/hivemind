from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic import Epic
from app.models.guard import Guard, TaskGuard
from app.models.epic_run import EpicRun
from app.models.epic_run_artifact import EpicRunArtifact
from app.models.task import Task
from app.services.epic_run_service import ACTIVE_TASK_STATES, EpicRunService

SCRATCHPAD_ARTIFACT = "scratchpad"
HANDOFF_ARTIFACT = "handoff_note"
FILE_CLAIM_ARTIFACT = "file_claim"
RESUME_PACKAGE_ARTIFACT = "resume_package"
ACTIVE_ARTIFACT_STATE = "active"
RELEASED_ARTIFACT_STATE = "released"


class EpicRunContextService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._analysis_helper = EpicRunService(db)

    async def ensure_epic_scratchpad(self, run_id: uuid.UUID) -> EpicRunArtifact:
        run = await self._get_run(run_id)
        stmt = select(EpicRunArtifact).where(
            EpicRunArtifact.epic_run_id == run.id,
            EpicRunArtifact.artifact_type == SCRATCHPAD_ARTIFACT,
            EpicRunArtifact.task_id.is_(None),
        )
        result = await self.db.execute(stmt)
        artifact = result.scalar_one_or_none()
        if artifact is not None:
            return artifact

        artifact = EpicRunArtifact(
            id=uuid.uuid4(),
            epic_run_id=run.id,
            epic_id=run.epic_id,
            artifact_type=SCRATCHPAD_ARTIFACT,
            state=ACTIVE_ARTIFACT_STATE,
            source_role="system",
            title="Epic Scratchpad",
            summary="Gemeinsame Annahmen, API-Vertraege und Risiken fuer diesen Epic-Run.",
            payload={
                "assumptions": [],
                "api_contracts": [],
                "risks": [],
                "notes": [],
            },
        )
        self.db.add(artifact)
        await self.db.flush()
        await self.db.refresh(artifact)
        return artifact

    async def create_worker_handoff(
        self,
        run_id: uuid.UUID,
        task: Task,
        *,
        execution_mode: str,
        trigger_detail: str,
        summary_suffix: str | None = None,
    ) -> EpicRunArtifact:
        summary = (
            f"Dispatch fuer {task.task_key} via {execution_mode}; "
            f"Trigger: {trigger_detail}."
        )
        if summary_suffix:
            summary = f"{summary} {summary_suffix}".strip()
        artifact = EpicRunArtifact(
            id=uuid.uuid4(),
            epic_run_id=run_id,
            epic_id=task.epic_id,
            task_id=task.id,
            artifact_type=HANDOFF_ARTIFACT,
            state=ACTIVE_ARTIFACT_STATE,
            source_role="system",
            target_role="worker",
            title=f"Handoff fuer {task.task_key}",
            summary=summary,
            payload={
                "task_key": task.task_key,
                "task_title": task.title,
                "task_state": task.state,
                "trigger_detail": trigger_detail,
                "execution_mode": execution_mode,
                "definition_of_done": (task.definition_of_done or {}).get("criteria", []),
                "review_comment": task.review_comment,
                "qa_failed_count": task.qa_failed_count or 0,
            },
        )
        self.db.add(artifact)
        await self.db.flush()
        await self.db.refresh(artifact)
        return artifact

    async def create_resume_package(
        self,
        task: Task,
        *,
        review_comment: str,
    ) -> EpicRunArtifact | None:
        run = await self._get_latest_run_for_epic(task.epic_id)
        if run is None:
            return None

        latest_existing = await self._get_latest_artifact_for_task(
            run.id,
            task.id,
            RESUME_PACKAGE_ARTIFACT,
        )
        if latest_existing is not None and latest_existing.state == ACTIVE_ARTIFACT_STATE:
            self._release_artifact(latest_existing)

        current_snapshot = self._snapshot_task_artifacts(task)
        previous_snapshot = []
        if latest_existing is not None:
            previous_snapshot = list((latest_existing.payload or {}).get("artifact_snapshot") or [])

        payload = {
            "task_key": task.task_key,
            "attempt_number": task.qa_failed_count or 0,
            "review_comment": review_comment,
            "guard_failures": await self._collect_guard_failures(task.id),
            "changed_files": self._extract_changed_files(task),
            "artifact_snapshot": current_snapshot,
            "artifact_diff": self._build_artifact_diff(previous_snapshot, current_snapshot),
            "open_dod_gaps": self._collect_open_dod_gaps(task),
            "result_excerpt": (task.result or "")[:2000],
        }
        artifact = EpicRunArtifact(
            id=uuid.uuid4(),
            epic_run_id=run.id,
            epic_id=task.epic_id,
            task_id=task.id,
            artifact_type=RESUME_PACKAGE_ARTIFACT,
            state=ACTIVE_ARTIFACT_STATE,
            source_role="reviewer",
            target_role="worker",
            title=f"Resume Paket fuer {task.task_key}",
            summary=(
                f"QA #{task.qa_failed_count or 0}: {review_comment[:220]}"
            ),
            payload=payload,
        )
        self.db.add(artifact)
        await self.db.flush()
        await self.db.refresh(artifact)
        return artifact

    async def sync_file_claims(self, run_id: uuid.UUID) -> dict[str, int]:
        run = await self._get_run(run_id)
        tasks = await self._load_epic_tasks(run.epic_id)

        existing_result = await self.db.execute(
            select(EpicRunArtifact).where(
                EpicRunArtifact.epic_run_id == run.id,
                EpicRunArtifact.artifact_type == FILE_CLAIM_ARTIFACT,
            )
        )
        existing = list(existing_result.scalars().all())
        existing_by_task_id = {
            artifact.task_id: artifact
            for artifact in existing
            if artifact.task_id is not None
        }

        active_count = 0
        released_count = 0
        desired_task_ids: set[uuid.UUID] = set()

        for task in tasks:
            claims = self._analysis_helper._extract_file_claims(task)
            if task.state not in ACTIVE_TASK_STATES or not claims:
                artifact = existing_by_task_id.get(task.id)
                if artifact is not None and artifact.state != RELEASED_ARTIFACT_STATE:
                    self._release_artifact(artifact)
                    released_count += 1
                continue

            desired_task_ids.add(task.id)
            artifact = existing_by_task_id.get(task.id)
            summary = self._build_file_claim_summary(task.task_key, claims)
            payload = {
                "task_key": task.task_key,
                "task_state": task.state,
                "claims": claims,
            }

            if artifact is None:
                artifact = EpicRunArtifact(
                    id=uuid.uuid4(),
                    epic_run_id=run.id,
                    epic_id=run.epic_id,
                    task_id=task.id,
                    artifact_type=FILE_CLAIM_ARTIFACT,
                    state=ACTIVE_ARTIFACT_STATE,
                    source_role="worker",
                    title=f"File Claims fuer {task.task_key}",
                    summary=summary,
                    payload=payload,
                )
                self.db.add(artifact)
            else:
                artifact.state = ACTIVE_ARTIFACT_STATE
                artifact.source_role = "worker"
                artifact.title = f"File Claims fuer {task.task_key}"
                artifact.summary = summary
                artifact.payload = payload
                artifact.released_at = None
            active_count += 1

        for artifact in existing:
            if artifact.task_id is None or artifact.task_id in desired_task_ids:
                continue
            if artifact.state != RELEASED_ARTIFACT_STATE:
                self._release_artifact(artifact)
                released_count += 1

        await self.db.flush()
        return {"active": active_count, "released": released_count}

    async def list_artifacts(
        self,
        run_id: uuid.UUID,
        *,
        artifact_type: str | None = None,
        state: str | None = None,
        task_key: str | None = None,
    ) -> list[dict[str, Any]]:
        await self.ensure_epic_scratchpad(run_id)
        await self.sync_file_claims(run_id)

        stmt: Select = (
            select(EpicRunArtifact, Task.task_key)
            .outerjoin(Task, EpicRunArtifact.task_id == Task.id)
            .where(EpicRunArtifact.epic_run_id == run_id)
            .order_by(EpicRunArtifact.created_at.asc())
        )
        if artifact_type:
            stmt = stmt.where(EpicRunArtifact.artifact_type == artifact_type)
        if state:
            stmt = stmt.where(EpicRunArtifact.state == state)
        if task_key:
            stmt = stmt.where(Task.task_key == task_key)

        result = await self.db.execute(stmt)
        return [
            self._serialize_artifact(artifact, resolved_task_key)
            for artifact, resolved_task_key in result.all()
        ]

    async def get_worker_shared_context(self, task: Task) -> dict[str, Any]:
        run = await self._get_latest_run_for_epic(task.epic_id)
        if run is None:
            return {
                "run_id": None,
                "scratchpad": [],
                "resume_package": None,
                "handoffs": [],
                "file_claims": {"own_claims": [], "active_related_claims": []},
            }

        await self.ensure_epic_scratchpad(run.id)
        await self.sync_file_claims(run.id)
        artifacts = await self._load_run_artifacts(run.id)

        own_claims = self._analysis_helper._extract_file_claims(task)
        scratchpads = [
            self._serialize_artifact(artifact, None)
            for artifact in artifacts
            if artifact.artifact_type == SCRATCHPAD_ARTIFACT
            and artifact.state == ACTIVE_ARTIFACT_STATE
        ]
        resume_package = next(
            (
                self._serialize_artifact(artifact, task.task_key)
                for artifact in reversed(artifacts)
                if artifact.artifact_type == RESUME_PACKAGE_ARTIFACT
                and artifact.task_id == task.id
            ),
            None,
        )
        handoffs = [
            self._serialize_artifact(artifact, task.task_key)
            for artifact in artifacts
            if artifact.artifact_type == HANDOFF_ARTIFACT
            and artifact.state == ACTIVE_ARTIFACT_STATE
            and artifact.task_id == task.id
            and (artifact.target_role in (None, "worker"))
        ]

        related_claims: list[dict[str, Any]] = []
        for artifact in artifacts:
            if (
                artifact.artifact_type != FILE_CLAIM_ARTIFACT
                or artifact.state != ACTIVE_ARTIFACT_STATE
                or artifact.task_id in (None, task.id)
            ):
                continue

            payload = dict(artifact.payload or {})
            other_claims = payload.get("claims") or []
            conflicts = (
                self._analysis_helper._find_file_claim_conflicts(own_claims, other_claims)
                if own_claims
                else []
            )
            if own_claims and not conflicts:
                continue
            related_claims.append(
                {
                    "task_key": payload.get("task_key"),
                    "task_state": payload.get("task_state"),
                    "summary": artifact.summary,
                    "claims": other_claims,
                    "conflicts": conflicts,
                }
            )

        return {
            "run_id": str(run.id),
            "scratchpad": scratchpads[:1],
            "resume_package": resume_package,
            "handoffs": handoffs[-3:],
            "file_claims": {
                "own_claims": own_claims,
                "active_related_claims": related_claims[:5],
            },
        }

    async def get_latest_resume_package(self, task: Task) -> dict[str, Any] | None:
        run = await self._get_latest_run_for_epic(task.epic_id)
        if run is None:
            return None
        artifact = await self._get_latest_artifact_for_task(
            run.id,
            task.id,
            RESUME_PACKAGE_ARTIFACT,
        )
        if artifact is None:
            return None
        return self._serialize_artifact(artifact, task.task_key)

    async def verify_run_access(self, run_id: uuid.UUID, actor: Any) -> EpicRun:
        run = await self._get_run(run_id)
        epic_result = await self.db.execute(select(Epic).where(Epic.id == run.epic_id))
        epic = epic_result.scalar_one_or_none()
        if epic is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Epic fuer Run '{run_id}' nicht gefunden.",
            )
        EpicRunService._ensure_access(epic.owner_id, epic.backup_owner_id, actor)
        return run

    async def _get_run(self, run_id: uuid.UUID) -> EpicRun:
        result = await self.db.execute(select(EpicRun).where(EpicRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"EpicRun '{run_id}' nicht gefunden.",
            )
        return run

    async def _get_latest_run_for_epic(self, epic_id: uuid.UUID) -> EpicRun | None:
        result = await self.db.execute(
            select(EpicRun)
            .where(EpicRun.epic_id == epic_id, EpicRun.dry_run.is_(False))
            .order_by(desc(EpicRun.started_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _load_epic_tasks(self, epic_id: uuid.UUID) -> list[Task]:
        result = await self.db.execute(
            select(Task).where(Task.epic_id == epic_id).order_by(Task.created_at.asc())
        )
        return list(result.scalars().all())

    async def _load_run_artifacts(self, run_id: uuid.UUID) -> list[EpicRunArtifact]:
        result = await self.db.execute(
            select(EpicRunArtifact)
            .where(EpicRunArtifact.epic_run_id == run_id)
            .order_by(EpicRunArtifact.created_at.asc())
        )
        return list(result.scalars().all())

    async def _get_latest_artifact_for_task(
        self,
        run_id: uuid.UUID,
        task_id: uuid.UUID,
        artifact_type: str,
    ) -> EpicRunArtifact | None:
        result = await self.db.execute(
            select(EpicRunArtifact)
            .where(
                EpicRunArtifact.epic_run_id == run_id,
                EpicRunArtifact.task_id == task_id,
                EpicRunArtifact.artifact_type == artifact_type,
            )
            .order_by(desc(EpicRunArtifact.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _release_artifact(artifact: EpicRunArtifact) -> None:
        artifact.state = RELEASED_ARTIFACT_STATE
        artifact.released_at = datetime.now(UTC)

    @staticmethod
    def _build_file_claim_summary(task_key: str, claims: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for claim in claims:
            paths = ", ".join(claim.get("paths", [])[:3])
            claim_type = str(claim.get("claim_type") or "exclusive")
            parts.append(f"{claim_type}: {paths}")
        summary = "; ".join(parts) if parts else "Keine deklarativen Claims."
        return f"{task_key}: {summary}"

    @staticmethod
    def _serialize_artifact(
        artifact: EpicRunArtifact,
        task_key: str | None,
    ) -> dict[str, Any]:
        return {
            "id": str(artifact.id),
            "epic_run_id": str(artifact.epic_run_id),
            "epic_id": str(artifact.epic_id),
            "task_id": str(artifact.task_id) if artifact.task_id else None,
            "task_key": task_key or (artifact.payload or {}).get("task_key"),
            "artifact_type": artifact.artifact_type,
            "state": artifact.state,
            "source_role": artifact.source_role,
            "target_role": artifact.target_role,
            "title": artifact.title,
            "summary": artifact.summary,
            "payload": artifact.payload or {},
            "created_at": artifact.created_at,
            "updated_at": artifact.updated_at,
            "released_at": artifact.released_at,
        }

    async def _collect_guard_failures(self, task_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(TaskGuard, Guard)
            .join(Guard, TaskGuard.guard_id == Guard.id)
            .where(TaskGuard.task_id == task_id)
        )
        failures: list[dict[str, Any]] = []
        for task_guard, guard in result.all():
            if task_guard.status == "passed":
                continue
            failures.append(
                {
                    "guard_id": str(task_guard.guard_id),
                    "title": guard.title,
                    "status": task_guard.status,
                    "result": task_guard.result,
                }
            )
        return failures

    @staticmethod
    def _snapshot_task_artifacts(task: Task) -> list[str]:
        snapshot: list[str] = []
        for artifact in task.artifacts or []:
            snapshot.append(str(artifact))
        return snapshot

    @staticmethod
    def _build_artifact_diff(
        previous_snapshot: list[str],
        current_snapshot: list[str],
    ) -> dict[str, list[str]]:
        previous = set(previous_snapshot)
        current = set(current_snapshot)
        return {
            "added": sorted(current - previous),
            "removed": sorted(previous - current),
        }

    @staticmethod
    def _collect_open_dod_gaps(task: Task) -> list[dict[str, Any]]:
        criteria = list(((task.definition_of_done or {}).get("criteria") or []))
        if not criteria:
            return []
        return [
            {"criterion": str(criterion), "status": "open"}
            for criterion in criteria
        ]

    @staticmethod
    def _extract_changed_files(task: Task) -> list[str]:
        files: list[str] = []
        for artifact in task.artifacts or []:
            if not isinstance(artifact, dict):
                continue
            for key in ("file", "files", "path", "paths", "target", "targets"):
                value = artifact.get(key)
                if isinstance(value, list):
                    files.extend(str(item) for item in value if str(item).strip())
                elif value:
                    files.append(str(value))
        deduped: list[str] = []
        for item in files:
            if item not in deduped:
                deduped.append(item)
        return deduped
