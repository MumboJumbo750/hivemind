from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from app.db import AsyncSessionLocal
from app.models.epic import Epic
from app.models.epic_run import EpicRun
from app.models.epic_run_artifact import EpicRunArtifact
from app.models.prompt_history import PromptHistory
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.services.epic_run_context import EpicRunContextService
from app.services.prompt_generator import PromptGenerator


async def _seed_epic_run_context_data() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as db:
        user = User(username=f"epic-run-{suffix}", role="admin")
        db.add(user)
        await db.flush()
        project = Project(
            name=f"Project {suffix}",
            slug=f"project-{suffix}",
            created_by=user.id,
        )
        db.add(project)
        await db.flush()

        epic = Epic(
            epic_key=f"EPIC-CONTEXT-{suffix.upper()}",
            project_id=project.id,
            title="Epic Run Context",
            state="in_progress",
            owner_id=user.id,
        )
        db.add(epic)
        await db.flush()

        task_primary = Task(
            task_key=f"TASK-CONTEXT-{suffix.upper()}-A",
            epic_id=epic.id,
            title="Primary task",
            state="in_progress",
            qa_failed_count=1,
            review_comment="Resume mit DoD-Luecken noetig.",
            definition_of_done={"criteria": ["Shared context appears in prompt"]},
            artifacts=[
                {
                    "kind": "file_claim",
                    "path": "backend/app/services/epic_run_service.py",
                    "claim_type": "exclusive",
                }
            ],
        )
        task_other = Task(
            task_key=f"TASK-CONTEXT-{suffix.upper()}-B",
            epic_id=epic.id,
            title="Secondary task",
            state="in_progress",
            artifacts=[
                {
                    "kind": "file_claim",
                    "path": "backend/app/services/epic_run_service.py",
                    "claim_type": "exclusive",
                }
            ],
        )
        db.add_all([task_primary, task_other])
        await db.flush()

        run = EpicRun(
            id=uuid.uuid4(),
            epic_id=epic.id,
            started_by=user.id,
            status="running",
            dry_run=False,
            config={"resolved_execution_mode": "byoai", "respect_file_claims": True},
            analysis={},
        )
        db.add(run)
        await db.flush()

        context_service = EpicRunContextService(db)
        scratchpad = await context_service.ensure_epic_scratchpad(run.id)
        scratchpad.payload = {
            "assumptions": ["Run verwendet strukturierte Artefakte statt Chat."],
            "api_contracts": ["Scheduler aktualisiert Scratchpad vor Worker-Dispatch."],
            "risks": ["Konflikt auf epic_run_service.py beachten."],
            "notes": [],
        }
        scratchpad.summary = "Gemeinsame Koordination fuer diesen Run."
        await context_service.create_worker_handoff(
            run.id,
            task_primary,
            execution_mode="byoai",
            trigger_detail="epic_run_scheduler:ready->in_progress",
        )
        await context_service.create_resume_package(
            task_primary,
            review_comment="Resume mit DoD-Luecken noetig.",
        )
        await context_service.sync_file_claims(run.id)
        await db.commit()

        return {
            "user_id": str(user.id),
            "project_id": str(project.id),
            "epic_id": str(epic.id),
            "task_primary_id": str(task_primary.id),
            "task_primary_key": task_primary.task_key,
            "task_other_id": str(task_other.id),
            "run_id": str(run.id),
        }


async def _cleanup_epic_run_context_data(data: dict[str, str]) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(PromptHistory).where(
                PromptHistory.task_id.in_(
                    [uuid.UUID(data["task_primary_id"]), uuid.UUID(data["task_other_id"])]
                )
            )
        )
        await db.execute(delete(EpicRunArtifact).where(EpicRunArtifact.epic_run_id == uuid.UUID(data["run_id"])))
        await db.execute(delete(EpicRun).where(EpicRun.id == uuid.UUID(data["run_id"])))
        await db.execute(
            delete(Task).where(
                Task.id.in_([uuid.UUID(data["task_primary_id"]), uuid.UUID(data["task_other_id"])])
            )
        )
        await db.execute(delete(Epic).where(Epic.id == uuid.UUID(data["epic_id"])))
        await db.execute(delete(Project).where(Project.id == uuid.UUID(data["project_id"])))
        await db.execute(delete(User).where(User.id == uuid.UUID(data["user_id"])))
        await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_epic_run_context_artifacts_are_listable_and_release_claims() -> None:
    data = await _seed_epic_run_context_data()
    try:
        async with AsyncSessionLocal() as db:
            svc = EpicRunContextService(db)
            artifacts = await svc.list_artifacts(uuid.UUID(data["run_id"]))
            assert {item["artifact_type"] for item in artifacts} == {
                "scratchpad",
                "handoff_note",
                "file_claim",
                "resume_package",
            }

            primary = await db.get(Task, uuid.UUID(data["task_primary_id"]))
            assert primary is not None
            primary.state = "done"
            await db.flush()
            await svc.sync_file_claims(uuid.UUID(data["run_id"]))
            refreshed = await svc.list_artifacts(
                uuid.UUID(data["run_id"]),
                artifact_type="file_claim",
                task_key=data["task_primary_key"],
            )
            await db.commit()

        assert refreshed[0]["state"] == "released"
        assert refreshed[0]["released_at"] is not None
    finally:
        await _cleanup_epic_run_context_data(data)


@pytest.mark.asyncio(loop_scope="session")
async def test_worker_prompt_includes_relevant_shared_context() -> None:
    data = await _seed_epic_run_context_data()
    try:
        async with AsyncSessionLocal() as db:
            generator = PromptGenerator(db)
            prompt = await generator.generate("worker", task_id=data["task_primary_key"])
            await db.commit()

        assert "### Shared Context" in prompt
        assert "Scratchpad" in prompt
        assert "Resume-Paket" in prompt
        assert "Handoffs" in prompt
        assert "Relevante aktive Claims anderer Tasks" in prompt
        assert "Konflikt moeglich" in prompt
    finally:
        await _cleanup_epic_run_context_data(data)
