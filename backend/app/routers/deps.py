"""FastAPI Dependencies für AuthN (TASK-2-003).

get_current_actor():  JWT Bearer Token validieren → CurrentActor zurückgeben.
get_optional_actor(): wie get_current_actor, gibt None wenn kein Token vorhanden.

Solo-Modus: wenn app_settings.hivemind_mode = 'solo', wird RBAC übersprungen
und ein System-Actor 'solo' zurückgegeben (TASK-2-004).
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.schemas.auth import CurrentActor
from app.services.auth_service import decode_token

bearer_scheme = HTTPBearer(auto_error=False)

_SOLO_ACTOR = CurrentActor(
    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    username="solo",
    role="admin",
)


async def _get_app_mode(db: AsyncSession) -> str:
    """Liest aktuellen Modus aus app_settings (gecacht wird in Phase 2 noch nicht)."""
    from sqlalchemy import text

    result = await db.execute(
        text("SELECT value FROM app_settings WHERE key = 'hivemind_mode' LIMIT 1")
    )
    row = result.one_or_none()
    return row[0] if row else "solo"


async def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor:
    """JWT validieren und CurrentActor zurückgeben. Im Solo-Modus: RBAC übersprungen."""
    mode = await _get_app_mode(db)
    if mode == "solo":
        return _SOLO_ACTOR

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht authentifiziert",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        if not user_id or not role:
            raise JWTError("Fehlende Claims")
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User nicht (mehr) gefunden",
        )

    return CurrentActor(id=user.id, username=user.username, role=role)


async def get_optional_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor | None:
    """Wie get_current_actor, gibt None zurück wenn kein Token vorhanden."""
    if not credentials:
        return None
    return await get_current_actor(credentials, db)


# Backwards-compat alias — Phase-1-Routers nutzen get_current_user
async def get_current_user(db: AsyncSession = Depends(get_db)) -> uuid.UUID:
    """Legacy Phase-1-Alias: gibt Actor-UUID zurück. Im Solo-Modus: solo-User-UUID."""
    actor = await get_current_actor(None, db)
    return actor.id


# ─── RBAC (TASK-2-004) ────────────────────────────────────────────────────────

def require_role(*roles: str):  # type: ignore[return]
    """Factory-Dependency: HTTP 403 wenn Actor-Rolle nicht in `roles`."""

    async def _check(actor: CurrentActor = Depends(get_current_actor)) -> CurrentActor:
        if actor.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unzureichende Rechte",
            )
        return actor

    return _check


async def require_project_access(
    project_id: uuid.UUID,
    actor: CurrentActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor:
    """Admin darf alles; Developer nur Projekte in denen er project_member ist."""
    if actor.role == "admin":
        return actor

    from app.models.project import ProjectMember

    result = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == actor.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Zugriff auf dieses Projekt",
        )
    return actor


async def require_task_access(
    task_key: str,
    actor: CurrentActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor:
    """Admin oder assigned Developer darf Task schreiben; sonst project_member-Check."""
    if actor.role == "admin":
        return actor

    from app.models.task import Task

    result = await db.execute(select(Task).where(Task.task_key == task_key))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task nicht gefunden")

    if task.assigned_to == actor.id:
        return actor  # assigned Developer darf eigenen Task bearbeiten

    from app.models.epic import Epic
    from app.models.project import ProjectMember

    epic_result = await db.execute(select(Epic).where(Epic.id == task.epic_id))
    epic = epic_result.scalar_one_or_none()
    if epic:
        member_result = await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == epic.project_id,
                ProjectMember.user_id == actor.id,
            )
        )
        if member_result.scalar_one_or_none():
            return actor

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Kein Zugriff auf diesen Task",
    )
