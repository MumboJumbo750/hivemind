from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.review_workflow import reject_task_review


@pytest.mark.asyncio
async def test_reject_task_review_creates_resume_package() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    task = SimpleNamespace(
        id=uuid.uuid4(),
        task_key="TASK-RESUME-1",
        state="in_review",
        qa_failed_count=0,
        review_comment=None,
        version=2,
        epic_id=uuid.uuid4(),
        result="Initial result",
    )
    resume_package = SimpleNamespace(id=uuid.uuid4())

    with patch(
        "app.services.epic_run_context.EpicRunContextService.create_resume_package",
        AsyncMock(return_value=resume_package),
    ) as create_resume, \
        patch(
            "app.services.learning_artifacts.create_execution_learning_artifacts",
            AsyncMock(),
        ) as create_execution, \
        patch(
            "app.services.learning_artifacts.create_learning_artifact",
            AsyncMock(),
        ), \
        patch(
            "app.services.learning_artifacts.record_learning_outcome_for_task",
            AsyncMock(),
        ) as record_outcome, \
        patch("app.services.review_workflow.publish"), \
        patch("app.services.conductor.conductor.on_task_state_change", AsyncMock()):
        payload = await reject_task_review(db, task, comment="DoD noch offen")

    assert task.state == "qa_failed"
    assert task.qa_failed_count == 1
    assert task.review_comment == "DoD noch offen"
    assert payload["resume_package_id"] == str(resume_package.id)
    create_resume.assert_awaited_once()
    create_execution.assert_awaited_once()
    record_outcome.assert_awaited_once()
