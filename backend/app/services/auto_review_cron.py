"""Auto-Review Cron — Phase 8 (TASK-8-008).

Checks for ReviewRecommendations with expired grace periods and auto-approves them.

Rules:
- Auto-approve only if: recommendation='approve' AND confidence >= threshold AND NOT vetoed
- Auto-reject NEVER happens automatically
- Moves task from in_review to done (via state machine) only if auto_approved=True

Registered in scheduler.py when HIVEMIND_CONDUCTOR_ENABLED=true.
"""
import logging
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

AUTO_APPROVE_CONFIDENCE_THRESHOLD = 0.75  # default threshold


async def auto_review_job() -> None:
    """APScheduler job: process expired grace periods and auto-approve where eligible."""
    from app.db import AsyncSessionLocal
    from sqlalchemy import select, and_
    from app.models.review import ReviewRecommendation
    from app.models.task import Task
    from app.services.governance import get_governance_level
    from app.services.review_workflow import approve_task_review

    now = datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        # Find expired grace periods: approve recommendations where:
        # - grace_period_until < now
        # - auto_approved = false
        # - vetoed_at is NULL
        # - recommendation = 'approve'
        result = await db.execute(
            select(ReviewRecommendation).where(
                and_(
                    ReviewRecommendation.grace_period_until <= now,
                    ReviewRecommendation.auto_approved == False,
                    ReviewRecommendation.vetoed_at.is_(None),
                    ReviewRecommendation.recommendation == "approve",
                )
            ).limit(50)
        )
        recs = result.scalars().all()

        for rec in recs:
            try:
                # Check governance level
                review_level = await get_governance_level(db, "review")
                if review_level != "auto":
                    # Only auto-approve if governance.review = 'auto'
                    continue

                # Check confidence threshold
                if rec.confidence < AUTO_APPROVE_CONFIDENCE_THRESHOLD:
                    logger.info(
                        "Auto-review: skipping %s — confidence %.2f below threshold %.2f",
                        rec.id, rec.confidence, AUTO_APPROVE_CONFIDENCE_THRESHOLD,
                    )
                    continue

                # Get the task
                task_result = await db.execute(
                    select(Task).where(Task.id == rec.task_id)
                )
                task = task_result.scalar_one_or_none()
                if not task:
                    logger.warning("Auto-review: task %s not found for rec %s", rec.task_id, rec.id)
                    continue

                # Only auto-approve tasks that are still in_review
                if task.state != "in_review":
                    logger.debug("Auto-review: task %s not in_review (state=%s) — skipping", task.task_key, task.state)
                    rec.auto_approved = True  # mark as processed anyway
                    continue

                # Apply canonical approve path so EXP, epic completion and follow-up dispatches run.
                await approve_task_review(
                    db,
                    task,
                    comment="Auto-approved after grace period",
                )
                rec.auto_approved = True

                logger.info(
                    "Auto-review: task %s auto-approved (confidence=%.2f, grace expired %s)",
                    task.task_key, rec.confidence, rec.grace_period_until,
                )

            except Exception as e:
                logger.error("Auto-review error for rec %s: %s", rec.id, e)

        await db.commit()
