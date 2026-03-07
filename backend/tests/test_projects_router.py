from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.main import app
from app.db import get_db
from app.routers.deps import get_current_user


@pytest.mark.asyncio
async def test_create_project_accepts_repo_fields(client) -> None:
    actor_id = uuid.uuid4()
    fake_db = AsyncMock()

    async def _override_db():
        yield fake_db

    async def _override_current_user():
        return actor_id

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user

    try:
        response_project = type(
            "ProjectObj",
            (),
            {
                "id": uuid.uuid4(),
                "name": "Repo Project",
                "slug": "repo-project",
                "description": "desc",
                "repo_host_path": "C:/code/repo-project",
                "workspace_root": "/workspace",
                "workspace_mode": "read_only",
                "onboarding_status": "pending",
                "default_branch": "main",
                "remote_url": "https://example.test/repo.git",
                "detected_stack": ["python", "vue"],
                "agent_thread_overrides": {"worker": "attempt_stateful"},
                "created_by": actor_id,
                "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            },
        )()

        with pytest.MonkeyPatch.context() as mp:
            create_mock = AsyncMock(return_value=response_project)
            mp.setattr("app.services.project_service.ProjectService.create", create_mock)
            response = await client.post(
                "/api/projects/",
                json={
                    "name": "Repo Project",
                    "slug": "repo-project",
                    "description": "desc",
                    "repo_host_path": "C:/code/repo-project",
                    "workspace_mode": "read_only",
                    "default_branch": "main",
                    "remote_url": "https://example.test/repo.git",
                    "detected_stack": ["python", "vue"],
                    "agent_thread_overrides": {"worker": "attempt_stateful"},
                },
            )

        assert response.status_code == 201
        payload = response.json()
        assert payload["repo_host_path"] == "C:/code/repo-project"
        assert payload["workspace_mode"] == "read_only"
        assert payload["onboarding_status"] == "pending"
        assert payload["agent_thread_overrides"] == {"worker": "attempt_stateful"}
        create_mock.assert_awaited_once()
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
