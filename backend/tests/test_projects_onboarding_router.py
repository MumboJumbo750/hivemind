from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.main import app
from app.db import get_db


@pytest.mark.asyncio
async def test_preview_project_onboarding_route(client) -> None:
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_db

    try:
        result = {
            "project_id": str(uuid.uuid4()),
            "project_slug": "repo-project",
            "repo_host_path": "C:/code/repo-project",
            "container_path": "/workspace",
            "workspace_mode": "read_only",
            "repo_accessible": False,
            "repo_is_git_repo": False,
            "detected_stack": [],
            "requires_restart": True,
            "warnings": ["warn"],
            "files": [
                {
                    "path": "docker-compose.override.yml",
                    "location": "hivemind_root",
                    "writable": True,
                    "content": "services:\n",
                }
            ],
            "next_steps": ["Restart backend"],
        }
        with pytest.MonkeyPatch.context() as mp:
            preview_mock = AsyncMock(return_value=result)
            mp.setattr("app.services.project_onboarding.ProjectOnboardingService.preview", preview_mock)
            response = await client.post(f"/api/projects/{uuid.uuid4()}/onboarding/preview", json={})

        assert response.status_code == 200
        assert response.json()["requires_restart"] is True
        preview_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
