from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.db import AsyncSessionLocal
from app.mcp.tools.admin_write_tools import _handle_merge_guard
from app.mcp.tools.worker_write_tools import _handle_report_guard_result
from app.mcp.tools.write_tools import _handle_update_task_state
from app.models.context_boundary import TaskSkill
from app.models.epic import Epic
from app.models.federation import Node
from app.models.guard import Guard, TaskGuard
from app.models.project import Project
from app.models.settings import AppSettings
from app.models.skill import Skill
from app.models.task import Task
from app.models.user import User
from app.services.guard_materialization import materialize_task_guards


async def _seed_guard_data(
    *,
    with_active_guards: bool = True,
    with_draft_guard: bool = False,
) -> dict[str, str | None]:
    suffix = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as db:
        previous_phase = await db.get(AppSettings, "current_phase")
        previous_phase_value = previous_phase.value if previous_phase else None

        user = User(username=f"guard-user-{suffix}", role="admin")
        node = Node(
            node_name=f"guard-node-{suffix}",
            node_url=f"http://guard-{suffix}.local:8000",
        )
        db.add_all([user, node])
        await db.flush()

        project = Project(
            name=f"Guard Project {suffix}",
            slug=f"guard-project-{suffix}",
            created_by=user.id,
        )
        db.add(project)
        await db.flush()

        epic = Epic(
            epic_key=f"EPIC-GUARD-{suffix.upper()}",
            project_id=project.id,
            title=f"Guard Epic {suffix}",
            state="in_progress",
            origin_node_id=node.id,
        )
        db.add(epic)
        await db.flush()

        task = Task(
            task_key=f"TASK-GUARD-{suffix.upper()}",
            epic_id=epic.id,
            title="Guarded task",
            description="Task for guard materialization tests",
            state="in_progress",
            result="Implemented result",
            pinned_skills=[f"guard-skill-{suffix}"],
        )
        db.add(task)
        await db.flush()

        skill = Skill(
            title=f"Guard Skill {suffix}",
            source_slug=f"guard-skill-{suffix}",
            content="## Guard skill\n\nBackend skill.",
            service_scope=["backend"],
            lifecycle="active",
            origin_node_id=node.id,
        )
        db.add(skill)
        await db.flush()

        db.add(TaskSkill(task_id=task.id, skill_id=skill.id))

        guards: list[Guard] = []
        if with_active_guards:
            guards.extend(
                [
                    Guard(
                        title=f"Global Guard {suffix}",
                        lifecycle="active",
                        created_by=user.id,
                    ),
                    Guard(
                        title=f"Project Guard {suffix}",
                        lifecycle="active",
                        project_id=project.id,
                        created_by=user.id,
                    ),
                    Guard(
                        title=f"Skill Guard {suffix}",
                        lifecycle="active",
                        skill_id=skill.id,
                        scope=["backend"],
                        created_by=user.id,
                    ),
                    Guard(
                        title=f"Frontend Guard {suffix}",
                        lifecycle="active",
                        scope=["frontend"],
                        created_by=user.id,
                    ),
                ]
            )

        draft_guard = None
        if with_draft_guard:
            draft_guard = Guard(
                title=f"Draft Guard {suffix}",
                lifecycle="draft",
                skill_id=skill.id,
                scope=["backend"],
                created_by=user.id,
            )
            guards.append(draft_guard)

        db.add_all(guards)

        if previous_phase is None:
            db.add(AppSettings(key="current_phase", value="5"))
        else:
            previous_phase.value = "5"

        await db.commit()

        skill_guard = next(
            (guard for guard in guards if guard.title.startswith("Skill Guard")),
            None,
        )

        return {
            "suffix": suffix,
            "user_id": str(user.id),
            "node_id": str(node.id),
            "project_id": str(project.id),
            "epic_id": str(epic.id),
            "task_id": str(task.id),
            "task_key": task.task_key,
            "skill_id": str(skill.id),
            "skill_guard_id": str(skill_guard.id) if skill_guard else None,
            "draft_guard_id": str(draft_guard.id) if draft_guard else None,
            "previous_phase_value": previous_phase_value,
        }


async def _cleanup_guard_data(data: dict[str, str | None]) -> None:
    async with AsyncSessionLocal() as db:
        task_id = uuid.UUID(data["task_id"])
        epic_id = uuid.UUID(data["epic_id"])
        project_id = uuid.UUID(data["project_id"])
        skill_id = uuid.UUID(data["skill_id"])
        node_id = uuid.UUID(data["node_id"])
        user_id = uuid.UUID(data["user_id"])
        guard_ids = list(
            (
                await db.execute(select(Guard.id).where(Guard.created_by == user_id))
            ).scalars().all()
        )

        await db.execute(delete(TaskGuard).where(TaskGuard.task_id == task_id))
        if guard_ids:
            await db.execute(delete(TaskGuard).where(TaskGuard.guard_id.in_(guard_ids)))
        await db.execute(delete(TaskSkill).where(TaskSkill.task_id == task_id))
        await db.execute(delete(Task).where(Task.id == task_id))
        await db.execute(delete(Guard).where(Guard.created_by == user_id))
        await db.execute(delete(Skill).where(Skill.id == skill_id))
        await db.execute(delete(Epic).where(Epic.id == epic_id))
        await db.execute(delete(Project).where(Project.id == project_id))
        await db.execute(delete(Node).where(Node.id == node_id))
        await db.execute(delete(User).where(User.id == user_id))

        previous_phase_value = data.get("previous_phase_value")
        if previous_phase_value is None:
            await db.execute(delete(AppSettings).where(AppSettings.key == "current_phase"))
        else:
            current_phase = await db.get(AppSettings, "current_phase")
            if current_phase:
                current_phase.value = previous_phase_value

        await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_materialize_task_guards_applies_global_project_and_skill_guards() -> None:
    data = await _seed_guard_data(with_active_guards=True)
    try:
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, uuid.UUID(data["task_id"]))
            created = await materialize_task_guards(db, task)
            await db.commit()

        assert created == 3

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(TaskGuard, Guard)
                    .join(Guard, TaskGuard.guard_id == Guard.id)
                    .where(TaskGuard.task_id == uuid.UUID(data["task_id"]))
                    .order_by(Guard.title.asc())
                )
            ).all()

        assert [guard.title for _, guard in rows] == [
            f"Global Guard {data['suffix']}",
            f"Project Guard {data['suffix']}",
            f"Skill Guard {data['suffix']}",
        ]
        assert all(task_guard.status == "pending" for task_guard, _ in rows)
    finally:
        await _cleanup_guard_data(data)


@pytest.mark.asyncio(loop_scope="session")
async def test_report_guard_result_materializes_missing_task_guard() -> None:
    data = await _seed_guard_data(with_active_guards=True)
    try:
        result = await _handle_report_guard_result(
            {
                "task_key": data["task_key"],
                "guard_id": data["skill_guard_id"],
                "status": "passed",
                "result": "lint ok",
            }
        )
        payload = json.loads(result[0].text)
        assert payload["data"]["status"] == "passed"

        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(TaskGuard, Guard)
                    .join(Guard, TaskGuard.guard_id == Guard.id)
                    .where(TaskGuard.task_id == uuid.UUID(data["task_id"]))
                    .order_by(Guard.title.asc())
                )
            ).all()

        assert len(rows) == 3
        assert any(
            guard.id == uuid.UUID(data["skill_guard_id"])
            and task_guard.status == "passed"
            and task_guard.result == "lint ok"
            for task_guard, guard in rows
        )
    finally:
        await _cleanup_guard_data(data)


@pytest.mark.asyncio(loop_scope="session")
async def test_merge_guard_materializes_and_review_gate_enforces_new_guard() -> None:
    data = await _seed_guard_data(with_active_guards=False, with_draft_guard=True)
    try:
        merge_result = await _handle_merge_guard({"guard_id": data["draft_guard_id"]})
        merge_payload = json.loads(merge_result[0].text)
        assert merge_payload["data"]["lifecycle"] == "active"
        assert merge_payload["data"]["tasks_materialized"] == 1

        with patch("app.services.conductor.conductor.on_task_state_change", new=AsyncMock()):
            blocked_result = await _handle_update_task_state(
                {"task_key": data["task_key"], "target_state": "in_review"}
            )
        blocked_payload = json.loads(blocked_result[0].text)
        assert blocked_payload["error"]["code"] == "GUARDS_NOT_PASSED"

        async with AsyncSessionLocal() as db:
            task_guard = (
                await db.execute(
                    select(TaskGuard).where(
                        TaskGuard.task_id == uuid.UUID(data["task_id"]),
                        TaskGuard.guard_id == uuid.UUID(data["draft_guard_id"]),
                    )
                )
            ).scalar_one()
            task_guard.status = "passed"
            task_guard.result = "guard ok"
            await db.commit()

        with patch("app.services.conductor.conductor.on_task_state_change", new=AsyncMock()):
            success_result = await _handle_update_task_state(
                {"task_key": data["task_key"], "target_state": "in_review"}
            )
        success_payload = json.loads(success_result[0].text)
        assert success_payload["data"]["state"] == "in_review"
    finally:
        await _cleanup_guard_data(data)
