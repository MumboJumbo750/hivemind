from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.tools.reviewer_tools import (
    handle_submit_review_recommendation,
    handle_veto_auto_review,
)
from app.services.governance import (
    maybe_auto_demote_review_governance,
    maybe_auto_promote_review_governance,
)


def _scalar_one(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalar_rows(rows: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


@pytest.mark.asyncio
async def test_maybe_auto_promote_review_governance_promotes_after_streak() -> None:
    row = SimpleNamespace(value=json.dumps({"review": "assisted"}))
    recommendations = [
        SimpleNamespace(recommendation="approve", vetoed_at=None, confidence=0.96)
        for _ in range(3)
    ]

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_one(row), _scalar_rows(recommendations)])
    db.flush = AsyncMock()

    with patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_enabled",
        True,
    ), patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_min_consecutive_approves",
        3,
    ), patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_min_confidence",
        0.9,
    ), patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_evaluation_window_days",
        30,
    ), patch(
        "app.services.notification_service.get_admin_user_ids",
        AsyncMock(return_value=[uuid.uuid4()]),
    ), patch(
        "app.services.notification_service.notify_users",
        AsyncMock(),
    ) as notify_users:
        promoted = await maybe_auto_promote_review_governance(db)

    assert promoted is True
    assert json.loads(row.value)["review"] == "auto"
    db.flush.assert_awaited_once()
    notify_users.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_auto_promote_review_governance_requires_clean_streak() -> None:
    row = SimpleNamespace(value=json.dumps({"review": "assisted"}))
    recommendations = [
        SimpleNamespace(recommendation="approve", vetoed_at=None, confidence=0.97),
        SimpleNamespace(recommendation="reject", vetoed_at=None, confidence=0.99),
        SimpleNamespace(recommendation="approve", vetoed_at=None, confidence=0.98),
    ]

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_scalar_one(row), _scalar_rows(recommendations)])
    db.flush = AsyncMock()

    with patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_enabled",
        True,
    ), patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_min_consecutive_approves",
        3,
    ), patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_min_confidence",
        0.9,
    ), patch(
        "app.services.notification_service.get_admin_user_ids",
        AsyncMock(return_value=[uuid.uuid4()]),
    ), patch(
        "app.services.notification_service.notify_users",
        AsyncMock(),
    ) as notify_users:
        promoted = await maybe_auto_promote_review_governance(db)

    assert promoted is False
    assert json.loads(row.value)["review"] == "assisted"
    db.flush.assert_not_awaited()
    notify_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_auto_demote_review_governance_demotes_and_notifies() -> None:
    row = SimpleNamespace(value=json.dumps({"review": "auto"}))

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_one(row))
    db.flush = AsyncMock()

    with patch.object(
        __import__("app.config", fromlist=["settings"]).settings,
        "hivemind_governance_auto_promotion_enabled",
        True,
    ), patch(
        "app.services.notification_service.get_admin_user_ids",
        AsyncMock(return_value=[uuid.uuid4()]),
    ), patch(
        "app.services.notification_service.notify_users",
        AsyncMock(),
    ) as notify_users:
        demoted = await maybe_auto_demote_review_governance(db)

    assert demoted is True
    assert json.loads(row.value)["review"] == "assisted"
    db.flush.assert_awaited_once()
    notify_users.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_submit_review_recommendation_reports_promotion_flag() -> None:
    task = SimpleNamespace(id=uuid.uuid4(), task_key="TASK-42", epic_id=uuid.uuid4())
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_one(task))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()

    with patch("app.services.governance.get_governance_level", AsyncMock(return_value="assisted")), \
         patch("app.services.learning_artifacts.create_learning_artifact", AsyncMock()), \
         patch("app.services.learning_artifacts.create_execution_learning_artifacts", AsyncMock()), \
         patch("app.services.governance.maybe_auto_promote_review_governance", AsyncMock(return_value=True)) as promote:
        payload = await handle_submit_review_recommendation(
            task_key="TASK-42",
            recommendation="approve",
            confidence=0.95,
            reasoning="Looks good",
            checklist=[{"item": "DoD", "passed": True, "comment": "ok"}],
            reviewer_dispatch_id=None,
            db=db,
            actor_id=str(uuid.uuid4()),
        )

    assert payload["governance_level"] == "auto"
    assert payload["governance_promoted"] is True
    promote.assert_awaited_once_with(db)


@pytest.mark.asyncio
async def test_handle_veto_auto_review_reports_demotion_flag() -> None:
    recommendation_id = str(uuid.uuid4())
    recommendation = SimpleNamespace(
        id=uuid.UUID(recommendation_id),
        auto_approved=False,
        vetoed_at=None,
        vetoed_by=None,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_one(recommendation))
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    with patch("app.services.governance.maybe_auto_demote_review_governance", AsyncMock(return_value=True)) as demote:
        payload = await handle_veto_auto_review(
            recommendation_id=recommendation_id,
            db=db,
            actor_id=str(uuid.uuid4()),
        )

    assert payload["vetoed"] is True
    assert payload["governance_demoted"] is True
    demote.assert_awaited_once_with(db)