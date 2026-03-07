from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db import get_db
from app.main import app


@pytest.mark.asyncio
async def test_sentry_webhook_persists_project_context(client) -> None:
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db

    try:
        outbox_id = uuid.uuid4()
        integration_id = uuid.uuid4()
        project_id = uuid.uuid4()
        entry = SimpleNamespace(id=outbox_id)

        payload = {
            "project": {"slug": "core-api"},
            "data": {
                "issue": {"id": "ISSUE-42", "title": "Unhandled Exception"},
                "event": {"event_id": "evt-42", "title": "Unhandled Exception", "level": "error"},
            },
        }

        with pytest.MonkeyPatch.context() as mp:
            resolve_mock = AsyncMock(
                return_value={
                    "matched": True,
                    "project_id": str(project_id),
                    "project_slug": "core-api",
                    "integration_id": str(integration_id),
                    "integration_key": "core-api-sentry",
                    "matched_by": "selector",
                    "reason": None,
                }
            )
            add_mock = AsyncMock(return_value=entry)
            audit_mock = AsyncMock()
            accepted_mock = AsyncMock()

            mp.setattr("app.routers.webhooks.get_outbox_by_dedup_key", AsyncMock(return_value=None))
            mp.setattr("app.routers.webhooks.add_outbox_entry", add_mock)
            mp.setattr("app.routers.webhooks.write_audit", audit_mock)
            mp.setattr(
                "app.services.project_integration_service.ProjectIntegrationService.resolve_inbound_target",
                resolve_mock,
            )
            mp.setattr(
                "app.services.project_integration_service.ProjectIntegrationService.mark_inbound_accepted",
                accepted_mock,
            )

            response = await client.post("/api/webhooks/sentry", json=payload)

        assert response.status_code == 202
        kwargs = add_mock.await_args.kwargs
        assert kwargs["project_id"] == project_id
        assert kwargs["integration_id"] == integration_id
        assert kwargs["payload"]["project_context"]["project_slug"] == "core-api"
        assert kwargs["routing_detail"]["matched_by"] == "selector"
        accepted_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
