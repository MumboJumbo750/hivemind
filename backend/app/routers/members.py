"""project_members CRUD-Endpoints (TASK-2-008).

POST   /api/projects/{id}/members
GET    /api/projects/{id}/members
PATCH  /api/projects/{id}/members/{user_id}
DELETE /api/projects/{id}/members/{user_id}
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.schemas.members import MemberAdd, MemberResponse, MemberUpdate
from app.schemas.project import ProjectMemberAdd
from app.services.auth_service import get_user_by_id
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["members"])


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID):
    return await ProjectService(db).get(project_id)


def _require_project_admin(actor: CurrentActor, project) -> None:
    """Admin oder Project-Owner darf Members verwalten."""
    if actor.role == "admin":
        return
    if project.created_by == actor.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Nur Admin oder Project-Owner darf Members verwalten",
    )


@router.post(
    "/{project_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    project_id: uuid.UUID,
    body: MemberAdd,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> MemberResponse:
    project = await _get_project_or_404(db, project_id)
    _require_project_admin(actor, project)

    # User existiert?
    if not await get_user_by_id(db, body.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")

    member = await ProjectService(db).add_member(
        project_id, ProjectMemberAdd(user_id=body.user_id, role=body.role)
    )
    return member  # type: ignore[return-value]


@router.get("/{project_id}/members", response_model=list[MemberResponse])
async def list_members(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> list[MemberResponse]:
    await _get_project_or_404(db, project_id)
    return await ProjectService(db).list_members(project_id)  # type: ignore[return-value]


@router.patch("/{project_id}/members/{user_id}", response_model=MemberResponse)
async def update_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    body: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> MemberResponse:
    project = await _get_project_or_404(db, project_id)
    _require_project_admin(actor, project)

    member = await ProjectService(db).update_member_role(project_id, user_id, body.role)
    return member  # type: ignore[return-value]


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> None:
    project = await _get_project_or_404(db, project_id)
    _require_project_admin(actor, project)

    await ProjectService(db).remove_member(project_id, user_id)
