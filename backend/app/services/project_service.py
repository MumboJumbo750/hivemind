import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectMember
from app.schemas.project import ProjectCreate, ProjectMemberAdd, ProjectUpdate


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
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def update(self, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
        project = await self.get(project_id)
        if data.name is not None:
            project.name = data.name
        if data.description is not None:
            project.description = data.description
        await self.db.flush()
        await self.db.refresh(project)
        return project

    async def list_members(self, project_id: uuid.UUID) -> list[ProjectMember]:
        result = await self.db.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
        return list(result.scalars().all())

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
