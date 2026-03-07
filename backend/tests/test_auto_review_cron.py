from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _SessionCtx:
    def __init__(self, db: AsyncMock) -> None:
        self._db = db

    async def __aenter__(self) -> AsyncMock:
        return self._db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _scalar_rows(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def _scalar_one(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_auto_review_job_uses_canonical_approve_workflow() -> None:
    recommendation = SimpleNamespace(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        confidence=0.9,
        grace_period_until=None,
        auto_approved=False,
        vetoed_at=None,
        recommendation="approve",
    )
    task = SimpleNamespace(
        id=recommendation.task_id,
        task_key="TASK-88",
        state="in_review",
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _scalar_rows([recommendation]),
            _scalar_one(task),
        ]
    )

    with patch("app.db.AsyncSessionLocal", new=lambda: _SessionCtx(db)), \
         patch("app.services.governance.get_governance_level", AsyncMock(return_value="auto")), \
         patch("app.services.review_workflow.approve_task_review", AsyncMock(return_value={"task_key": "TASK-88"})) as approve:
        from app.services.auto_review_cron import auto_review_job

        await auto_review_job()

    approve.assert_awaited_once_with(
        db,
        task,
        comment="Auto-approved after grace period",
    )
    assert recommendation.auto_approved is True
    db.commit.assert_awaited_once()
