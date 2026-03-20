import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectMember
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectMemberAdd, ProjectMemberResponse, ProjectUpdate
from app.services.agent_threading import normalize_thread_policy

DEFAULT_WORKSPACE_ROOT = "/workspace"
DEFAULT_WORKSPACE_MODE = "read_only"


class ProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_all(self) -> list[Project]:
        result = await self.db.execute(select(Project).order_by(Project.created_at.desc()))
        return list(result.scalars().all())

    async def get(self, project_id: uuid.UUID) -> Project:
        result = await self.db.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden.")
        return project

    async def create(self, data: ProjectCreate, created_by: uuid.UUID) -> Project:
        # Check slug uniqueness
        existing = await self.db.execute(select(Project).where(Project.slug == data.slug))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Slug '{data.slug}' ist bereits vergeben.",
            )
        project = Project(
            name=data.name,
            slug=data.slug,
            description=data.description,
            created_by=created_by,
        )
        self._apply_repo_fields(project, data)
        project.agent_thread_overrides = self._normalize_thread_overrides(
            getattr(data, "agent_thread_overrides", None)
        )
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def update(self, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
        project = await self.get(project_id)
        fields_set = data.model_fields_set
        if "name" in fields_set and data.name is not None:
            project.name = data.name
        if "description" in fields_set:
            project.description = data.description
        if "agent_thread_overrides" in fields_set:
            project.agent_thread_overrides = self._normalize_thread_overrides(
                data.agent_thread_overrides
            )
        self._apply_repo_fields(project, data)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def list_members(self, project_id: uuid.UUID) -> list[ProjectMemberResponse]:
        result = await self.db.execute(
            select(ProjectMember, User.username)
            .outerjoin(User, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id == project_id)
        )
        rows = result.all()
        if not rows:
            # Solo-Modus: Creator automatisch als Member eintragen
            project = await self.get(project_id)
            if project.created_by:
                member = ProjectMember(
                    project_id=project_id,
                    user_id=project.created_by,
                    role="admin",
                )
                self.db.add(member)
                await self.db.flush()
                # Username nachschlagen
                user_result = await self.db.execute(
                    select(User.username).where(User.id == project.created_by)
                )
                username = user_result.scalar_one_or_none()
                return [ProjectMemberResponse(
                    project_id=project_id,
                    user_id=project.created_by,
                    role="admin",
                    username=username,
                )]
        return [
            ProjectMemberResponse(
                project_id=m.project_id,
                user_id=m.user_id,
                role=m.role,
                username=username,
            )
            for m, username in rows
        ]

    async def add_member(self, project_id: uuid.UUID, data: ProjectMemberAdd) -> ProjectMember:
        # Ensure project exists
        await self.get(project_id)
        existing = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == data.user_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User ist bereits Mitglied.",
            )
        member = ProjectMember(project_id=project_id, user_id=data.user_id, role=data.role)
        self.db.add(member)
        await self.db.flush()
        return member

    async def update_member_role(
        self, project_id: uuid.UUID, user_id: uuid.UUID, role: str
    ) -> ProjectMember:
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitglied nicht gefunden.")
        member.role = role
        await self.db.flush()
        return member

    async def remove_member(self, project_id: uuid.UUID, user_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitglied nicht gefunden.")
        await self.db.delete(member)

    async def get_member_or_none(self, project_id: uuid.UUID, user_id: uuid.UUID) -> ProjectMember | None:
        """Gibt ProjectMember zurück oder None (kein 403/404)."""
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    def _apply_repo_fields(self, project: Project, data: ProjectCreate | ProjectUpdate) -> None:
        fields_set = getattr(data, "model_fields_set", set())

        if isinstance(data, ProjectCreate):
            repo_supplied = bool(data.repo_host_path)
            project.repo_host_path = data.repo_host_path
            project.workspace_root = data.workspace_root or (DEFAULT_WORKSPACE_ROOT if repo_supplied else None)
            project.workspace_mode = data.workspace_mode or (DEFAULT_WORKSPACE_MODE if repo_supplied else None)
            project.onboarding_status = data.onboarding_status or ("pending" if repo_supplied else None)
            project.default_branch = data.default_branch
            project.remote_url = data.remote_url
            project.detected_stack = data.detected_stack
            return

        if "repo_host_path" in fields_set:
            project.repo_host_path = data.repo_host_path
            if not data.repo_host_path:
                project.workspace_root = None
                project.workspace_mode = None
                project.onboarding_status = None
                project.default_branch = None
                project.remote_url = None
                project.detected_stack = None
                return

        repo_is_configured = bool(project.repo_host_path)

        if "workspace_root" in fields_set:
            project.workspace_root = data.workspace_root
        elif repo_is_configured and not project.workspace_root:
            project.workspace_root = DEFAULT_WORKSPACE_ROOT

        if "workspace_mode" in fields_set:
            project.workspace_mode = data.workspace_mode
        elif repo_is_configured and not project.workspace_mode:
            project.workspace_mode = DEFAULT_WORKSPACE_MODE

        if "onboarding_status" in fields_set:
            project.onboarding_status = data.onboarding_status
        elif repo_is_configured and not project.onboarding_status:
            project.onboarding_status = "pending"

        if "default_branch" in fields_set:
            project.default_branch = data.default_branch
        if "remote_url" in fields_set:
            project.remote_url = data.remote_url
        if "detected_stack" in fields_set:
            project.detected_stack = data.detected_stack

    def _normalize_thread_overrides(self, overrides: dict[str, str] | None) -> dict[str, str]:
        if overrides is None:
            return {}
        normalized: dict[str, str] = {}
        for role, raw_policy in overrides.items():
            policy = normalize_thread_policy(raw_policy)
            if not policy:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Ungueltige Thread-Policy '{raw_policy}' fuer Rolle '{role}'.",
                )
            normalized[str(role).strip().lower()] = policy
        return normalized
