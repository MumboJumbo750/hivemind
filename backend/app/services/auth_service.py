"""JWT-Erstellung + Passwort-Hashing (TASK-2-002)."""
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.config import settings

# bcrypt in this runtime currently fails during passlib backend self-check.
# Use a stable passlib hash scheme for deterministic auth behavior.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.refresh_token_expire_days
    )
    return jwt.encode(
        {"sub": user_id, "type": "refresh", "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    """Validiert und dekodiert Token. Wirft JWTError bei Fehler."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


# ─── DB-Helfer (async) ───────────────────────────────────────────────────────
import uuid as _uuid

from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession


async def get_user_by_id(db: _AsyncSession, user_id: _uuid.UUID):
    """Gibt User per UUID zurück oder None."""
    from app.models.user import User
    return await db.get(User, user_id)


async def get_user_by_username(db: _AsyncSession, username: str):
    """Gibt User per Username zurück oder None."""
    from app.models.user import User
    result = await db.execute(_select(User).where(User.username == username).limit(1))
    return result.scalar_one_or_none()


async def get_any_user(db: _AsyncSession):
    """Gibt irgendeinen User zurück oder None (Solo-Fallback)."""
    from app.models.user import User
    result = await db.execute(_select(User).limit(1))
    return result.scalar_one_or_none()


async def create_user(
    db: _AsyncSession,
    user_id: _uuid.UUID,
    username: str,
    display_name: str | None,
    email: str | None,
    password_hash: str,
    role: str,
):
    """Erstellt und speichert einen neuen User (flush, kein commit)."""
    from app.models.user import User
    user = User(
        id=user_id,
        username=username,
        display_name=display_name,
        email=email,
        password_hash=password_hash,
        role=role,
    )
    db.add(user)
    await db.flush()
    return user


async def get_users_by_ids(
    db: _AsyncSession, user_ids: "set[_uuid.UUID]"
) -> "dict[_uuid.UUID, str]":
    """Gibt {user_id: username} für die gegebenen IDs zurück."""
    from app.models.user import User
    if not user_ids:
        return {}
    result = await db.execute(_select(User).where(User.id.in_(user_ids)))
    return {u.id: u.username for u in result.scalars().all()}
