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
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.schemas.auth import CurrentActor
from app.services import auth_service
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


async def _resolve_solo_actor(db: AsyncSession) -> CurrentActor:
    """Resolve solo actor to an existing DB user to keep FK writes valid.

    Preferred order:
    1) username='admin'
    2) any existing user
    3) static fallback actor (legacy behavior)
    """
    admin_user = await auth_service.get_user_by_username(db, "admin")
    if admin_user:
        return CurrentActor(
            id=admin_user.id,
            username=admin_user.username,
            role="admin",
        )

    any_user = await auth_service.get_any_user(db)
    if any_user:
        return CurrentActor(
            id=any_user.id,
            username=any_user.username,
            role="admin",
        )

    return _SOLO_ACTOR


async def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor:
    """JWT validieren und CurrentActor zurückgeben. Im Solo-Modus: RBAC übersprungen."""
    mode = await _get_app_mode(db)
    if mode == "solo":
        return await _resolve_solo_actor(db)

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

    user = await auth_service.get_user_by_id(db, uuid.UUID(user_id))
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

    from app.services.project_service import ProjectService

    if not await ProjectService(db).get_member_or_none(project_id, actor.id):
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

    from app.services.epic_service import EpicService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    task = await TaskService(db).get_by_key(task_key)

    if task.assigned_to == actor.id:
        return actor  # assigned Developer darf eigenen Task bearbeiten

    epic = await EpicService(db).get_by_id_or_none(task.epic_id)
    if epic:
        if await ProjectService(db).get_member_or_none(epic.project_id, actor.id):
            return actor

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Kein Zugriff auf diesen Task",
    )
