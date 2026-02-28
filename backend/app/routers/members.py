"""project_members CRUD-Endpoints (TASK-2-008).

POST   /api/projects/{id}/members
GET    /api/projects/{id}/members
PATCH  /api/projects/{id}/members/{user_id}
DELETE /api/projects/{id}/members/{user_id}
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.project import Project, ProjectMember
from app.models.user import User
from app.routers.deps import get_current_actor
from app.schemas.auth import CurrentActor
from app.schemas.members import MemberAdd, MemberResponse, MemberUpdate

router = APIRouter(prefix="/projects", tags=["members"])


async def _get_project_or_404(db: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projekt nicht gefunden")
    return project


def _require_project_admin(actor: CurrentActor, project: Project) -> None:
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
    user = await db.get(User, body.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User nicht gefunden")

    # Duplikat-Schutz
    existing = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User ist bereits Mitglied")

    member = ProjectMember(project_id=project_id, user_id=body.user_id, role=body.role)
    db.add(member)
    await db.flush()
    return member  # type: ignore[return-value]


@router.get("/{project_id}/members", response_model=list[MemberResponse])
async def list_members(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: CurrentActor = Depends(get_current_actor),
) -> list[MemberResponse]:
    await _get_project_or_404(db, project_id)
    result = await db.execute(
        select(ProjectMember).where(ProjectMember.project_id == project_id)
    )
    return list(result.scalars().all())  # type: ignore[return-value]


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

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitglied nicht gefunden")

    member.role = body.role
    await db.flush()
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

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mitglied nicht gefunden")

    await db.delete(member)
    await db.flush()
