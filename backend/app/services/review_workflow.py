"""Shared review workflow helpers used by MCP tools and auto-review."""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.services.event_bus import publish

logger = logging.getLogger(__name__)


async def approve_task_review(
    db: AsyncSession,
    task: Task,
    *,
    comment: str,
) -> dict[str, object]:
    """Approve a task review through the canonical side-effect path."""
    from app.services.learning_artifacts import record_learning_outcome_for_task

    if task.state != "in_review":
        raise ValueError(f"Task muss in_review sein, ist '{task.state}'")

    previous_state = task.state
    task.state = "done"
    task.version += 1

    exp_awarded = 50
    if task.assigned_to:
        await _award_exp(db, task.assigned_to, exp_awarded)

    await db.flush()

    publish(
        "task_done",
        {
            "task_key": task.task_key,
            "comment": comment,
            "exp_awarded": exp_awarded,
        },
        channel="tasks",
    )

    epic_transitioned = False
    if task.epic_id:
        epic_transitioned = await _check_epic_completion(db, task.epic_id)

    await record_learning_outcome_for_task(db, task=task, outcome="success")

    try:
        from app.services.conductor import conductor

        await conductor.on_task_state_change(
            task.task_key,
            str(task.id),
            previous_state,
            task.state,
            db,
        )
    except Exception:
        logger.exception("Conductor hook failed for review approve %s", task.task_key)

    return {
        "task_key": task.task_key,
        "state": "done",
        "exp_awarded": exp_awarded,
        "epic_auto_transitioned": epic_transitioned,
        "comment": comment,
    }


async def reject_task_review(
    db: AsyncSession,
    task: Task,
    *,
    comment: str,
) -> dict[str, object]:
    """Reject a task review through the canonical side-effect path."""
    from app.services.epic_run_context import EpicRunContextService
    from app.services.learning_artifacts import (
        create_execution_learning_artifacts,
        create_learning_artifact,
        record_learning_outcome_for_task,
    )

    if task.state != "in_review":
        raise ValueError(f"Task muss in_review sein, ist '{task.state}'")

    previous_state = task.state
    task.state = "qa_failed"
    task.qa_failed_count = (task.qa_failed_count or 0) + 1
    task.review_comment = comment
    task.version += 1

    await db.flush()
    resume_package = await EpicRunContextService(db).create_resume_package(task, review_comment=comment)
    await create_learning_artifact(
        db,
        artifact_type="review_feedback",
        source_type="task_review_reject",
        source_ref=task.task_key,
        agent_role="reviewer",
        epic_id=str(task.epic_id) if task.epic_id else None,
        task_id=str(task.id),
        summary=comment[:1200],
        detail={
            "task_key": task.task_key,
            "qa_failed_count": task.qa_failed_count,
        },
        confidence=0.75,
    )
    await create_execution_learning_artifacts(
        db,
        source_type="task_review_reject",
        source_ref=task.task_key,
        summary=comment[:1200],
        detail={
            "task_key": task.task_key,
            "qa_failed_count": task.qa_failed_count,
            "open_dod_gaps": (resume_package.payload or {}).get("open_dod_gaps", [])
            if resume_package is not None and hasattr(resume_package, "payload")
            else [],
            "guard_failures": (resume_package.payload or {}).get("guard_failures", [])
            if resume_package is not None and hasattr(resume_package, "payload")
            else [],
        },
        agent_role="reviewer",
        epic_id=str(task.epic_id) if task.epic_id else None,
        task_id=str(task.id),
    )

    publish(
        "task_qa_failed",
        {
            "task_key": task.task_key,
            "qa_failed_count": task.qa_failed_count,
            "comment": comment,
        },
        channel="tasks",
    )

    await record_learning_outcome_for_task(db, task=task, outcome="qa_failed")

    try:
        from app.services.conductor import conductor

        await conductor.on_task_state_change(
            task.task_key,
            str(task.id),
            previous_state,
            task.state,
            db,
        )
    except Exception:
        logger.exception("Conductor hook failed for review reject %s", task.task_key)

    return {
        "task_key": task.task_key,
        "state": "qa_failed",
        "qa_failed_count": task.qa_failed_count,
        "comment": comment,
        "resume_package_id": str(resume_package.id) if resume_package is not None else None,
    }


async def _award_exp(
    db: AsyncSession,
    user_id: uuid.UUID,
    amount: int,
) -> None:
    from app.models.user import User

    try:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.exp_points = (user.exp_points or 0) + amount
            await db.flush()
    except Exception:
        logger.exception("_award_exp failed (non-critical)")


async def _check_epic_completion(db: AsyncSession, epic_id: uuid.UUID) -> bool:
    from app.models.epic import Epic

    try:
        result = await db.execute(
            select(sa_func.count(Task.id))
            .where(Task.epic_id == epic_id)
            .where(Task.state.notin_(["done", "cancelled"]))
        )
        remaining = result.scalar()

        if remaining == 0:
            e_result = await db.execute(select(Epic).where(Epic.id == epic_id))
            epic = e_result.scalar_one_or_none()
            if epic and epic.state != "done":
                epic.state = "done"
                epic.version += 1
                await db.flush()
                publish(
                    "epic_done",
                    {"epic_key": epic.epic_key, "epic_id": str(epic_id)},
                    channel="epics",
                )
                return True
        return False
    except Exception:
        logger.exception("_check_epic_completion failed (non-critical)")
        return False
