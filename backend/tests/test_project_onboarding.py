from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services.project_onboarding import ProjectOnboardingService


@pytest.mark.asyncio
async def test_preview_returns_generated_files_for_accessible_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "package.json").write_text("{}", encoding="utf-8")
        (repo / "tsconfig.json").write_text("{}", encoding="utf-8")

        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="repo-project",
            repo_host_path=str(repo),
            workspace_mode="read_write",
        )
        db = AsyncMock()
        svc = ProjectOnboardingService(db)
        svc.project_service.get = AsyncMock(return_value=project)

        preview = await svc.preview(project.id)

        assert preview["repo_accessible"] is True
        assert preview["repo_is_git_repo"] is True
        assert "nodejs" in preview["detected_stack"]
        assert all(file["writable"] for file in preview["files"])


@pytest.mark.asyncio
async def test_preview_warns_for_inaccessible_windows_repo_path() -> None:
    project = SimpleNamespace(
        id=uuid.uuid4(),
        slug="repo-project",
        repo_host_path="C:\\code\\repo-project",
        workspace_mode="read_only",
    )
    db = AsyncMock()
    svc = ProjectOnboardingService(db)
    svc.project_service.get = AsyncMock(return_value=project)

    preview = await svc.preview(project.id)

    assert preview["repo_accessible"] is False
    assert preview["warnings"]
    assert any(not file["writable"] for file in preview["files"] if file["location"] == "repo_workspace")


@pytest.mark.asyncio
async def test_preview_uses_runtime_workspace_for_matching_windows_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime_root = Path(tmp) / "runtime-repo"
        (runtime_root / ".git").mkdir(parents=True)
        (runtime_root / "package.json").write_text("{}", encoding="utf-8")
        (runtime_root / ".git" / "config").write_text(
            "[remote \"origin\"]\n\turl = https://github.com/example/runtime-repo.git\n",
            encoding="utf-8",
        )
        (runtime_root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="repo-project",
            repo_host_path="C:\\code\\runtime-repo",
            workspace_mode="read_write",
            remote_url=None,
            default_branch=None,
            detected_stack=None,
        )
        db = AsyncMock()
        db.flush = AsyncMock()
        svc = ProjectOnboardingService(db)
        svc.project_service.get = AsyncMock(return_value=project)

        with patch("app.services.project_onboarding.settings.hivemind_workspace_root", str(runtime_root)):
            preview = await svc.preview(project.id)

        assert preview["repo_accessible"] is True
        assert preview["repo_is_git_repo"] is True
        assert any("Runtime-Workspace" in warning for warning in preview["warnings"])
        assert any(
            file["path"] == str(runtime_root / ".vscode" / "mcp.json") and file["writable"]
            for file in preview["files"]
            if file["location"] == "repo_workspace"
        )
        assert project.remote_url == "https://github.com/example/runtime-repo.git"
        assert project.default_branch == "main"
        assert db.flush.await_count == 1


@pytest.mark.asyncio
async def test_apply_writes_override_and_workspace_files_when_repo_accessible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir(parents=True)
        (repo / ".git").mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="repo-project",
            repo_host_path=str(repo),
            workspace_mode="read_only",
            workspace_root=None,
            onboarding_status=None,
            detected_stack=None,
        )

        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        svc = ProjectOnboardingService(db)
        svc.project_service.get = AsyncMock(return_value=project)

        with patch.object(svc, "_resolve_hivemind_root", return_value=Path(tmp) / "hivemind-root"):
            result = await svc.apply(project.id)

        assert project.onboarding_status == "pending"
        assert (Path(tmp) / "hivemind-root" / "docker-compose.override.yml").exists()
        assert (repo / ".vscode" / "mcp.json").exists()
        assert result["pending_files"] == []
        override_content = (Path(tmp) / "hivemind-root" / "docker-compose.override.yml").read_text(encoding="utf-8")
        assert f'"{repo.as_posix()}:/workspace:ro"' in override_content


@pytest.mark.asyncio
async def test_verify_sets_error_when_runtime_workspace_missing() -> None:
    project = SimpleNamespace(
        id=uuid.uuid4(),
        slug="repo-project",
        repo_host_path="/tmp/repo",
        workspace_mode="read_only",
        workspace_root="/workspace",
        onboarding_status="pending",
        detected_stack=[],
    )
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    svc = ProjectOnboardingService(db)
    svc.project_service.get = AsyncMock(return_value=project)

    with patch("app.services.project_onboarding.settings.hivemind_workspace_root", "/definitely/missing/path"):
        result = await svc.verify(project.id)

    assert result["status"] == "error"
    assert result["workspace_accessible"] is False


@pytest.mark.asyncio
async def test_verify_sets_error_when_runtime_workspace_points_to_other_repo() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime_root = Path(tmp) / "other-repo"
        (runtime_root / ".git").mkdir(parents=True)

        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="repo-project",
            repo_host_path="C:\\code\\target-repo",
            workspace_mode="read_only",
            workspace_root="/workspace",
            onboarding_status="pending",
            detected_stack=[],
            remote_url=None,
        )
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        svc = ProjectOnboardingService(db)
        svc.project_service.get = AsyncMock(return_value=project)

        with patch("app.services.project_onboarding.settings.hivemind_workspace_root", str(runtime_root)):
            result = await svc.verify(project.id)

    assert result["status"] == "error"
    assert result["workspace_accessible"] is True
    assert "passt aber nicht" in result["message"]


@pytest.mark.asyncio
async def test_verify_persists_repo_metadata_from_runtime_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runtime_root = Path(tmp) / "workspace"
        (runtime_root / ".git" / "refs" / "remotes" / "origin").mkdir(parents=True)
        (runtime_root / ".git" / "config").write_text(
            "[remote \"origin\"]\n\turl = https://github.com/example/hivemind.git\n",
            encoding="utf-8",
        )
        (runtime_root / ".git" / "refs" / "remotes" / "origin" / "HEAD").write_text(
            "ref: refs/remotes/origin/main\n",
            encoding="utf-8",
        )
        (runtime_root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="hivemind",
            repo_host_path="C:\\projects\\hivemind",
            workspace_mode="read_write",
            workspace_root="/workspace",
            onboarding_status="pending",
            detected_stack=None,
            remote_url=None,
            default_branch=None,
        )
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        svc = ProjectOnboardingService(db)
        svc.project_service.get = AsyncMock(return_value=project)

        with patch("app.services.project_onboarding.settings.hivemind_workspace_root", str(runtime_root)):
            result = await svc.verify(project.id)

    assert result["status"] == "ready"
    assert project.remote_url == "https://github.com/example/hivemind.git"
    assert project.default_branch == "main"
    assert "python" in project.detected_stack


@pytest.mark.asyncio
async def test_preview_requires_repo_path() -> None:
    project = SimpleNamespace(
        id=uuid.uuid4(),
        slug="repo-project",
        repo_host_path=None,
        workspace_mode="read_only",
    )
    db = AsyncMock()
    svc = ProjectOnboardingService(db)
    svc.project_service.get = AsyncMock(return_value=project)

    with pytest.raises(HTTPException) as exc:
        await svc.preview(project.id)

    assert exc.value.status_code == 422
