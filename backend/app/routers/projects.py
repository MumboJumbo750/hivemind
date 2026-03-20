import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_user
from app.schemas.project import (
    ProjectIntegrationCreate,
    ProjectIntegrationResponse,
    ProjectIntegrationUpdate,
    ProjectOnboardingApplyResponse,
    ProjectOnboardingPreviewResponse,
    ProjectOnboardingRequest,
    ProjectOnboardingStatusResponse,
    ProjectOnboardingVerifyResponse,
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.project_integration_service import ProjectIntegrationService
from app.services.project_service import ProjectService
from app.services.project_onboarding import ProjectOnboardingService

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
    return await svc.list_members(project_id)


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


@router.post("/{project_id}/onboarding/preview", response_model=ProjectOnboardingPreviewResponse)
async def preview_project_onboarding(
    project_id: uuid.UUID,
    body: ProjectOnboardingRequest,
    db: AsyncSession = Depends(get_db),
) -> ProjectOnboardingPreviewResponse:
    svc = ProjectOnboardingService(db)
    result = await svc.preview(
        project_id,
        port=body.port,
        container_path=body.container_path,
        deny_patterns=body.deny_patterns,
    )
    return ProjectOnboardingPreviewResponse.model_validate(result)


@router.post("/{project_id}/onboarding/apply", response_model=ProjectOnboardingApplyResponse)
async def apply_project_onboarding(
    project_id: uuid.UUID,
    body: ProjectOnboardingRequest,
    db: AsyncSession = Depends(get_db),
) -> ProjectOnboardingApplyResponse:
    svc = ProjectOnboardingService(db)
    result = await svc.apply(
        project_id,
        port=body.port,
        container_path=body.container_path,
        deny_patterns=body.deny_patterns,
    )
    return ProjectOnboardingApplyResponse.model_validate(result)


@router.post("/{project_id}/onboarding/verify", response_model=ProjectOnboardingVerifyResponse)
async def verify_project_onboarding(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProjectOnboardingVerifyResponse:
    svc = ProjectOnboardingService(db)
    result = await svc.verify(project_id)
    return ProjectOnboardingVerifyResponse.model_validate(result)


@router.get("/{project_id}/onboarding/status", response_model=ProjectOnboardingStatusResponse)
async def get_project_onboarding_status(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProjectOnboardingStatusResponse:
    svc = ProjectOnboardingService(db)
    result = await svc.status(project_id)
    return ProjectOnboardingStatusResponse.model_validate(result)


@router.get("/{project_id}/integrations", response_model=list[ProjectIntegrationResponse])
async def list_project_integrations(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ProjectIntegrationResponse]:
    svc = ProjectIntegrationService(db)
    return [ProjectIntegrationResponse.model_validate(item) for item in await svc.list_for_project(project_id)]


@router.post(
    "/{project_id}/integrations",
    response_model=ProjectIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_integration(
    project_id: uuid.UUID,
    body: ProjectIntegrationCreate,
    db: AsyncSession = Depends(get_db),
) -> ProjectIntegrationResponse:
    svc = ProjectIntegrationService(db)
    result = await svc.create(project_id, body)
    return ProjectIntegrationResponse.model_validate(result)


@router.patch("/{project_id}/integrations/{integration_id}", response_model=ProjectIntegrationResponse)
async def update_project_integration(
    project_id: uuid.UUID,
    integration_id: uuid.UUID,
    body: ProjectIntegrationUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProjectIntegrationResponse:
    svc = ProjectIntegrationService(db)
    result = await svc.update(project_id, integration_id, body)
    return ProjectIntegrationResponse.model_validate(result)


@router.post("/{project_id}/integrations/{integration_id}/check", response_model=ProjectIntegrationResponse)
async def check_project_integration(
    project_id: uuid.UUID,
    integration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProjectIntegrationResponse:
    svc = ProjectIntegrationService(db)
    result = await svc.check(project_id, integration_id)
    return ProjectIntegrationResponse.model_validate(result)
