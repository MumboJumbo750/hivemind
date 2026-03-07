from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import uuid

import pytest


@pytest.mark.asyncio
async def test_get_execution_learnings_returns_effectiveness_metrics(client) -> None:
    artifact = SimpleNamespace(
        id=uuid.uuid4(),
        summary="Review-Check: Tests aktualisieren",
        status="proposal",
        confidence=0.84,
        detail={
            "kind": "review_checklist",
            "audiences": ["reviewer", "worker"],
            "occurrence_count": 3,
            "effectiveness": {
                "prompt_inclusions": 5,
                "success_count": 2,
                "qa_failed_count": 1,
            },
        },
        created_at=datetime(2026, 3, 7, tzinfo=UTC),
    )

    with patch(
        "app.routers.kpis.list_execution_learning_artifacts",
        AsyncMock(return_value=[artifact]),
    ):
        response = await client.get("/api/kpis/execution-learnings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["summary"] == "Review-Check: Tests aktualisieren"
    assert payload["items"][0]["success_count"] == 2
    assert payload["items"][0]["prompt_inclusions"] == 5
