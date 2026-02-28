import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_user
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    svc = ProjectService(db)
    return await svc.list_all()  # type: ignore[return-value]


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: uuid.UUID = Depends(get_current_user),
) -> ProjectResponse:
    svc = ProjectService(db)
    return await svc.create(body, created_by=current_user)  # type: ignore[return-value]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    svc = ProjectService(db)
    return await svc.get(project_id)  # type: ignore[return-value]


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    svc = ProjectService(db)
    return await svc.update(project_id, body)  # type: ignore[return-value]


@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
async def list_members(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ProjectMemberResponse]:
    svc = ProjectService(db)
    return await svc.list_members(project_id)  # type: ignore[return-value]


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: uuid.UUID,
    body: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
) -> ProjectMemberResponse:
    svc = ProjectService(db)
    return await svc.add_member(project_id, body)  # type: ignore[return-value]


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberResponse)
async def update_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
) -> ProjectMemberResponse:
    svc = ProjectService(db)
    return await svc.update_member_role(project_id, user_id, body.role)  # type: ignore[return-value]


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = ProjectService(db)
    await svc.remove_member(project_id, user_id)
