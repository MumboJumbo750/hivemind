from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.project_integration_service import ProjectIntegrationService


@pytest.mark.asyncio
async def test_resolve_inbound_target_matches_sentry_by_slug() -> None:
    project_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    project = SimpleNamespace(id=project_id, slug="core-api")
    integration = SimpleNamespace(
        id=integration_id,
        project_id=project_id,
        integration_type="sentry",
        sync_enabled=True,
        integration_key="core-api-sentry",
        external_project_key="core-api",
        project_selector={"aliases": ["core-api-prod"]},
        display_name="Core API",
        base_url="https://sentry.example.com",
        status_mapping=None,
        routing_hints=None,
        config=None,
        github_repo=None,
        github_project_id=None,
        status_field_id=None,
        priority_field_id=None,
        webhook_secret=None,
        access_token=None,
        last_health_state=None,
        last_health_detail=None,
        health_checked_at=None,
        last_event_at=None,
        last_error_at=None,
        last_error_detail=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    scalar_result = MagicMock()
    scalar_result.all.return_value = [integration]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalar_result

    db = AsyncMock()
    db.execute.return_value = execute_result

    svc = ProjectIntegrationService(db)
    svc.project_service.get = AsyncMock(return_value=project)

    resolved = await svc.resolve_inbound_target(
        provider="sentry",
        normalized_payload={"project": "core-api-prod"},
        raw_payload={"project": {"slug": "core-api-prod"}},
    )

    assert resolved["matched"] is True
    assert resolved["project_slug"] == "core-api"
    assert resolved["integration_id"] == str(integration_id)
    assert resolved["matched_by"] == "selector"


@pytest.mark.asyncio
async def test_check_marks_incomplete_when_required_fields_missing() -> None:
    project_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    integration = SimpleNamespace(
        id=integration_id,
        project_id=project_id,
        integration_type="youtrack",
        display_name="YT",
        integration_key="yt-core",
        base_url=None,
        external_project_key=None,
        project_selector={},
        status_mapping=None,
        routing_hints=None,
        config=None,
        github_repo=None,
        github_project_id=None,
        status_field_id=None,
        priority_field_id=None,
        webhook_secret=None,
        access_token=None,
        sync_enabled=True,
        sync_direction="bidirectional",
        last_health_state=None,
        last_health_detail=None,
        health_checked_at=None,
        last_event_at=None,
        last_error_at=None,
        last_error_detail=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    db = AsyncMock()
    svc = ProjectIntegrationService(db)

    with patch.object(svc, "_get_integration", new=AsyncMock(return_value=integration)):
        result = await svc.check(project_id, integration_id)

    assert result["status"] == "incomplete"
    assert "base_url" in result["status_detail"]
    assert integration.last_health_state == "incomplete"
