from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.db import get_db
from app.main import app


@pytest.mark.asyncio
async def test_create_project_integration_route(client) -> None:
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db

    try:
        integration_id = uuid.uuid4()
        project_id = uuid.uuid4()
        result = {
            "id": str(integration_id),
            "project_id": str(project_id),
            "provider": "sentry",
            "display_name": "Core API Sentry",
            "integration_key": "core-api-sentry",
            "base_url": "https://sentry.example.com",
            "external_project_key": "core-api",
            "project_selector": {"aliases": ["core-api-prod"]},
            "status_mapping": None,
            "routing_hints": None,
            "config": None,
            "sync_enabled": True,
            "sync_direction": "bidirectional",
            "github_repo": None,
            "github_project_id": None,
            "status_field_id": None,
            "priority_field_id": None,
            "has_webhook_secret": True,
            "has_access_token": False,
            "status": "active",
            "status_detail": "Konfiguration vollständig",
            "last_health_state": None,
            "last_health_detail": None,
            "health_checked_at": None,
            "last_event_at": None,
            "last_error_at": None,
            "last_error_detail": None,
            "created_at": "2026-03-06T10:00:00Z",
            "updated_at": "2026-03-06T10:00:00Z",
        }
        with pytest.MonkeyPatch.context() as mp:
            create_mock = AsyncMock(return_value=result)
            mp.setattr("app.services.project_integration_service.ProjectIntegrationService.create", create_mock)
            response = await client.post(
                f"/api/projects/{project_id}/integrations",
                json={
                    "provider": "sentry",
                    "display_name": "Core API Sentry",
                    "integration_key": "core-api-sentry",
                    "external_project_key": "core-api",
                    "webhook_secret": "top-secret",
                },
            )

        assert response.status_code == 201
        assert response.json()["provider"] == "sentry"
        create_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
