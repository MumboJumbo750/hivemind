from __future__ import annotations

import configparser
import re
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import Project
from app.services.onboarding_templates import (
    DEFAULT_ONBOARDING_DENY_PATTERNS,
    DEFAULT_ONBOARDING_PORT,
    DEFAULT_WORKSPACE_ROOT_CONTAINER,
    cursor_mcp_json,
    docker_compose_override,
    hivemind_config_yml,
    normalize_workspace_host_path,
    vscode_mcp_json,
)
from app.services.project_service import ProjectService

HIVEMIND_ROOT = Path(__file__).resolve().parents[3]


class ProjectOnboardingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.project_service = ProjectService(db)

    async def preview(
        self,
        project_id,
        *,
        port: int = DEFAULT_ONBOARDING_PORT,
        container_path: str = DEFAULT_WORKSPACE_ROOT_CONTAINER,
        deny_patterns: str = DEFAULT_ONBOARDING_DENY_PATTERNS,
    ) -> dict:
        project = await self.project_service.get(project_id)
        repo_host_path = (project.repo_host_path or "").strip()
        if not repo_host_path:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Projekt hat noch keinen Repo-Pfad für das Onboarding.",
            )

        access = self._inspect_repo_path(project, repo_host_path)
        await self._sync_project_repo_metadata(project, access["resolved_path"])
        stack = self._detect_stack(access["resolved_path"]) if access["accessible"] else []

        files = self._build_file_plan(
            repo_host_path=repo_host_path,
            container_path=container_path,
            port=port,
            deny_patterns=deny_patterns,
            workspace_target_root=access["resolved_path"],
            write_workspace_files=access["workspace_files_writable"],
            workspace_mode=project.workspace_mode or "read_only",
        )

        warnings: list[str] = []
        if not access["accessible"]:
            warnings.append(
                "Repo-Pfad ist aus dem Backend-Container nicht direkt lesbar. "
                "Workspace-Dateien werden daher nur als Vorschau geliefert."
            )
        elif access["source"] == "runtime_workspace":
            warnings.append(
                "Repo-Pfad ist im Container nicht direkt lesbar. "
                "Der aktuelle Runtime-Workspace wird als Schreibziel verwendet."
            )
        elif not access["is_repo"]:
            warnings.append(
                "Pfad ist lesbar, aber es wurde kein .git-Verzeichnis erkannt."
            )

        return {
            "project_id": str(project.id),
            "project_slug": project.slug,
            "repo_host_path": repo_host_path,
            "container_path": container_path,
            "workspace_mode": project.workspace_mode or "read_only",
            "repo_accessible": access["accessible"],
            "repo_is_git_repo": access["is_repo"],
            "detected_stack": stack,
            "requires_restart": True,
            "warnings": warnings,
            "files": files,
            "next_steps": [
                "Onboarding anwenden oder Vorschau prüfen",
                "Backend neu starten, damit der neue Workspace-Mount aktiv wird",
                "Danach Verify ausführen",
            ],
        }

    async def apply(
        self,
        project_id,
        *,
        port: int = DEFAULT_ONBOARDING_PORT,
        container_path: str = DEFAULT_WORKSPACE_ROOT_CONTAINER,
        deny_patterns: str = DEFAULT_ONBOARDING_DENY_PATTERNS,
    ) -> dict:
        preview = await self.preview(
            project_id,
            port=port,
            container_path=container_path,
            deny_patterns=deny_patterns,
        )
        project = await self.project_service.get(project_id)

        applied_files: list[str] = []
        pending_files: list[str] = []
        for file_spec in preview["files"]:
            target = Path(file_spec["path"])
            if file_spec["writable"]:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(file_spec["content"], encoding="utf-8")
                applied_files.append(str(target))
            else:
                pending_files.append(str(target))

        project.workspace_root = container_path
        project.onboarding_status = "pending"
        if preview["detected_stack"]:
            project.detected_stack = preview["detected_stack"]
        await self.db.flush()
        await self.db.refresh(project)

        return {
            "project_id": str(project.id),
            "status": project.onboarding_status,
            "applied_files": applied_files,
            "pending_files": pending_files,
            "requires_restart": True,
            "message": "Onboarding-Dateien vorbereitet. Bitte Backend/Stack neu starten und danach verify ausführen.",
        }

    async def verify(self, project_id) -> dict:
        project = await self.project_service.get(project_id)
        runtime_root = Path(settings.hivemind_workspace_root)
        runtime_accessible = runtime_root.exists() and runtime_root.is_dir()
        runtime_match = (
            self._match_runtime_workspace(project, project.repo_host_path or "")
            if runtime_accessible and (project.repo_host_path or "").strip()
            else {"matched": runtime_accessible}
        )
        stack = self._detect_stack(runtime_root) if runtime_accessible else []

        warnings: list[str] = []
        if not runtime_accessible:
            project.onboarding_status = "error"
            message = (
                f"Workspace-Root '{settings.hivemind_workspace_root}' ist im Backend nicht erreichbar."
            )
        elif not runtime_match["matched"]:
            project.onboarding_status = "error"
            message = "Workspace im Backend erreichbar, passt aber nicht zum Projekt-Repo."
        else:
            project.onboarding_status = "ready"
            message = "Workspace im Backend erreichbar."
            await self._sync_project_repo_metadata(project, runtime_root)
            if not (runtime_root / ".git").exists():
                warnings.append("Workspace ist erreichbar, aber .git wurde nicht gefunden.")
            if runtime_match.get("reason") == "name":
                warnings.append(
                    "Workspace wurde heuristisch über den Verzeichnisnamen dem Projekt-Repo zugeordnet."
                )
            if runtime_match.get("reason") == "remote_repo_name":
                warnings.append(
                    "Workspace wurde heuristisch über den Git-Remote-Namen dem Projekt-Repo zugeordnet."
                )
            if project.detected_stack != stack and stack:
                project.detected_stack = stack

        project.workspace_root = settings.hivemind_workspace_root
        await self.db.flush()
        await self.db.refresh(project)

        return {
            "project_id": str(project.id),
            "status": project.onboarding_status,
            "workspace_root": settings.hivemind_workspace_root,
            "workspace_accessible": runtime_accessible,
            "detected_stack": stack,
            "warnings": warnings,
            "message": message,
        }

    async def status(self, project_id) -> dict:
        project = await self.project_service.get(project_id)
        runtime_root = Path(settings.hivemind_workspace_root)
        runtime_accessible = runtime_root.exists() and runtime_root.is_dir()
        return {
            "project_id": str(project.id),
            "status": project.onboarding_status,
            "repo_host_path": project.repo_host_path,
            "workspace_root": project.workspace_root,
            "runtime_workspace_root": settings.hivemind_workspace_root,
            "runtime_workspace_accessible": runtime_accessible,
            "detected_stack": project.detected_stack or [],
            "deny_patterns": [
                p.strip() for p in settings.hivemind_fs_deny_list.split(",") if p.strip()
            ],
        }

    def _inspect_repo_path(self, project: Project | None, repo_host_path: str) -> dict:
        normalized_host_path = normalize_workspace_host_path(repo_host_path)
        if self._looks_like_windows_path(repo_host_path):
            runtime_match = self._match_runtime_workspace(project, repo_host_path)
            if runtime_match["matched"]:
                return {
                    "accessible": True,
                    "is_repo": runtime_match["is_repo"],
                    "resolved_path": runtime_match["resolved_path"],
                    "source": "runtime_workspace",
                    "workspace_files_writable": True,
                    "normalized_host_path": normalized_host_path,
                }
            return {
                "accessible": False,
                "is_repo": False,
                "resolved_path": None,
                "source": "unavailable",
                "workspace_files_writable": False,
                "normalized_host_path": normalized_host_path,
            }

        path = Path(repo_host_path).expanduser()
        if not path.is_absolute():
            return {
                "accessible": False,
                "is_repo": False,
                "resolved_path": None,
                "source": "unavailable",
                "workspace_files_writable": False,
                "normalized_host_path": normalized_host_path,
            }

        accessible = path.exists() and path.is_dir()
        return {
            "accessible": accessible,
            "is_repo": accessible and (path / ".git").exists(),
            "resolved_path": path if accessible else None,
            "source": "host_path" if accessible else "unavailable",
            "workspace_files_writable": accessible,
            "normalized_host_path": normalized_host_path,
        }

    def _build_file_plan(
        self,
        *,
        repo_host_path: str,
        container_path: str,
        port: int,
        deny_patterns: str,
        workspace_target_root: Path | None,
        write_workspace_files: bool,
        workspace_mode: str,
    ) -> list[dict]:
        repo_target = workspace_target_root or Path(repo_host_path).expanduser()
        read_only = workspace_mode != "read_write"
        return [
            {
                "path": str(self._resolve_hivemind_root() / "docker-compose.override.yml"),
                "location": "hivemind_root",
                "writable": True,
                "content": docker_compose_override(repo_host_path, container_path, read_only=read_only),
            },
            {
                "path": str(repo_target / ".vscode" / "mcp.json"),
                "location": "repo_workspace",
                "writable": write_workspace_files,
                "content": vscode_mcp_json(port),
            },
            {
                "path": str(repo_target / ".cursor" / "mcp.json"),
                "location": "repo_workspace",
                "writable": write_workspace_files,
                "content": cursor_mcp_json(port),
            },
            {
                "path": str(repo_target / ".hivemind" / "config.yml"),
                "location": "repo_workspace",
                "writable": write_workspace_files,
                "content": hivemind_config_yml(repo_host_path, container_path, port, deny_patterns),
            },
        ]

    def _detect_stack(self, root: Path | None) -> list[str]:
        if root is None:
            return []

        stack: list[str] = []
        if (root / "package.json").exists():
            stack.append("nodejs")
        if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
            stack.append("python")
        if (root / "tsconfig.json").exists():
            stack.append("typescript")
        if (root / "vite.config.ts").exists() or (root / "vite.config.js").exists():
            stack.append("vite")
        if (root / "vue.config.js").exists() or (root / "src" / "App.vue").exists():
            stack.append("vue")
        if (root / ".git").exists():
            stack.append("git")
        return sorted(set(stack))

    def _looks_like_windows_path(self, value: str) -> bool:
        return bool(re.match(r"^[A-Za-z]:[\\/]", value)) or value.startswith("\\\\")

    def _resolve_hivemind_root(self) -> Path:
        candidates = [
            Path("/workspace"),
            HIVEMIND_ROOT,
            Path.cwd(),
        ]
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            if (candidate / "docker-compose.yml").exists() and (candidate / "backend").is_dir():
                return candidate
        return HIVEMIND_ROOT

    def _match_runtime_workspace(self, project: Project | None, repo_host_path: str) -> dict:
        runtime_root = Path(settings.hivemind_workspace_root)
        if not runtime_root.exists() or not runtime_root.is_dir():
            return {"matched": False, "resolved_path": None, "is_repo": False}

        normalized_repo_path = normalize_workspace_host_path(repo_host_path)
        runtime_host_path = self._read_runtime_host_path(runtime_root)
        if runtime_host_path and runtime_host_path == normalized_repo_path:
            return {
                "matched": True,
                "resolved_path": runtime_root,
                "is_repo": (runtime_root / ".git").exists(),
                "reason": "config",
            }

        project_remote_url = getattr(project, "remote_url", None) if project is not None else None
        if project_remote_url and project_remote_url.strip():
            runtime_remote = self._read_git_remote_url(runtime_root)
            if runtime_remote and runtime_remote.rstrip("/") == project_remote_url.strip().rstrip("/"):
                return {
                    "matched": True,
                    "resolved_path": runtime_root,
                    "is_repo": (runtime_root / ".git").exists(),
                    "reason": "remote_url",
                }

        runtime_remote = self._read_git_remote_url(runtime_root)
        runtime_repo_name = self._extract_repo_name_from_remote(runtime_remote)
        if runtime_repo_name:
            target_name = Path(normalized_repo_path).stem.lower()
            if target_name and runtime_repo_name == target_name:
                return {
                    "matched": True,
                    "resolved_path": runtime_root,
                    "is_repo": (runtime_root / ".git").exists(),
                    "reason": "remote_repo_name",
                }

        target_name = Path(normalized_repo_path).name.lower()
        if target_name and runtime_root.name.lower() == target_name:
            return {
                "matched": True,
                "resolved_path": runtime_root,
                "is_repo": (runtime_root / ".git").exists(),
                "reason": "name",
            }

        return {"matched": False, "resolved_path": None, "is_repo": False}

    def _read_runtime_host_path(self, runtime_root: Path) -> str | None:
        config_path = runtime_root / ".hivemind" / "config.yml"
        if not config_path.exists():
            return None
        text = config_path.read_text(encoding="utf-8")
        match = re.search(r'host_path:\s*"([^"]+)"', text)
        if not match:
            return None
        return normalize_workspace_host_path(match.group(1))

    def _read_git_remote_url(self, runtime_root: Path) -> str | None:
        git_config = runtime_root / ".git" / "config"
        if not git_config.exists():
            return None
        parser = configparser.ConfigParser()
        parser.read(git_config, encoding="utf-8")
        for section_name in ('remote "origin"',):
            if parser.has_option(section_name, "url"):
                return parser.get(section_name, "url").strip()
        return None

    def _read_default_branch(self, repo_root: Path) -> str | None:
        origin_head = repo_root / ".git" / "refs" / "remotes" / "origin" / "HEAD"
        for candidate in (origin_head, repo_root / ".git" / "HEAD"):
            if not candidate.exists():
                continue
            text = candidate.read_text(encoding="utf-8").strip()
            match = re.match(r"ref:\s+refs/(?:remotes/origin|heads)/(?P<branch>.+)", text)
            if match:
                return match.group("branch").strip()
        return None

    def _extract_repo_name_from_remote(self, remote_url: str | None) -> str | None:
        if not remote_url:
            return None
        cleaned = remote_url.rstrip("/").rsplit("/", 1)[-1]
        cleaned = cleaned.rsplit(":", 1)[-1]
        if cleaned.endswith(".git"):
            cleaned = cleaned[:-4]
        cleaned = cleaned.strip().lower()
        return cleaned or None

    async def _sync_project_repo_metadata(self, project: Project, repo_root: Path | None) -> None:
        if repo_root is None or not repo_root.exists():
            return

        changed = False
        remote_url = self._read_git_remote_url(repo_root)
        default_branch = self._read_default_branch(repo_root)
        stack = self._detect_stack(repo_root)

        if remote_url and getattr(project, "remote_url", None) != remote_url:
            project.remote_url = remote_url
            changed = True
        if default_branch and getattr(project, "default_branch", None) != default_branch:
            project.default_branch = default_branch
            changed = True
        if stack and getattr(project, "detected_stack", None) != stack:
            project.detected_stack = stack
            changed = True

        if changed:
            await self.db.flush()
