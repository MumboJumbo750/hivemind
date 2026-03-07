import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_create_project_sets_repo_defaults() -> None:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()

    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None
    db.execute.return_value = empty_result

    svc = ProjectService(db)
    project = await svc.create(
        ProjectCreate(
            name="Repo Project",
            slug="repo-project",
            repo_host_path="C:/code/repo-project",
        ),
        created_by=uuid.uuid4(),
    )

    assert project.repo_host_path == "C:/code/repo-project"
    assert project.workspace_root == "/workspace"
    assert project.workspace_mode == "read_only"
    assert project.onboarding_status == "pending"
    assert project.agent_thread_overrides == {}
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_project_rejects_duplicate_slug() -> None:
    db = AsyncMock()
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = object()
    db.execute.return_value = existing_result

    svc = ProjectService(db)

    with pytest.raises(HTTPException) as exc:
        await svc.create(
            ProjectCreate(name="Repo Project", slug="repo-project"),
            created_by=uuid.uuid4(),
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_project_clearing_repo_fields_resets_workspace_metadata() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    project = MagicMock()
    project.name = "Existing"
    project.description = "Desc"
    project.repo_host_path = "C:/code/repo-project"
    project.workspace_root = "/workspace"
    project.workspace_mode = "read_write"
    project.onboarding_status = "ready"
    project.default_branch = "main"
    project.remote_url = "https://example.test/repo.git"
    project.detected_stack = ["python", "vue"]

    svc = ProjectService(db)
    svc.get = AsyncMock(return_value=project)

    updated = await svc.update(
        uuid.uuid4(),
        ProjectUpdate(repo_host_path=None),
    )

    assert updated.repo_host_path is None
    assert updated.workspace_root is None
    assert updated.workspace_mode is None
    assert updated.onboarding_status is None
    assert updated.default_branch is None
    assert updated.remote_url is None
    assert updated.detected_stack is None


@pytest.mark.asyncio
async def test_update_project_normalizes_agent_thread_overrides() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    project = MagicMock()
    project.agent_thread_overrides = {}

    svc = ProjectService(db)
    svc.get = AsyncMock(return_value=project)

    updated = await svc.update(
        uuid.uuid4(),
        ProjectUpdate(agent_thread_overrides={"Worker": "attempt_stateful", "architekt": "stateless"}),
    )

    assert updated.agent_thread_overrides == {
        "worker": "attempt_stateful",
        "architekt": "stateless",
    }
