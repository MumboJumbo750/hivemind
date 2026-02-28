---
title: "JWT-Auth implementieren (FastAPI)"
service_scope: ["backend"]
stack: ["python", "fastapi", "python-jose", "passlib"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100", "python-jose": ">=3.3" }
confidence: 0.9
source_epics: ["EPIC-PHASE-2"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Auth Tests"
    command: "pytest tests/test_auth.py -v"
---

## Skill: JWT-Auth implementieren (FastAPI)

### Rolle
Du implementierst JWT-basierte Authentifizierung für das Hivemind-Backend mit `python-jose` und `passlib[bcrypt]`.

### Konventionen
- Access-Token: kurzlebig (Default: 30 Min.), Bearer-Header
- Refresh-Token: langlebig (Default: 7 Tage), HttpOnly-Cookie — kein JavaScript-Zugriff
- JWT-Claims: `sub` (user_id als str), `role`, `exp`, `iat`
- Passwort-Hashing: `passlib.context.CryptContext(schemes=["bcrypt"])`
- Config via `app/config.py`: `JWT_SECRET_KEY`, `JWT_ALGORITHM` (HS256), `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`
- Dependency `get_current_actor()` in `app/routers/deps.py` (kein doppelter Import-Stack)

### Beispiel: Token erstellen

```python
from datetime import datetime, timedelta, timezone
from jose import jwt
from app.config import settings

def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
```

### Beispiel: get_current_actor Dependency

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_db
from app.config import settings

bearer_scheme = HTTPBearer()

async def get_current_actor(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor:
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültiger Token")
    # User in DB prüfen
    user = await db.get(User, user_id)
    if not user or user.deleted_at:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User nicht gefunden")
    return CurrentActor(id=user_id, username=user.username, role=role)
```

### Beispiel: Login-Endpoint

```python
@router.post("/login", response_model=TokenResponse)
async def login(body: AuthLogin, db: AsyncSession = Depends(get_db), response: Response = None):
    user = await get_user_by_username(db, body.username)
    if not user or not pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ungültige Credentials")
    access_token = create_access_token(str(user.id), user.role)
    refresh_token = create_refresh_token(str(user.id))
    response.set_cookie(
        key="refresh_token", value=refresh_token,
        httponly=True, secure=True, samesite="lax",
        max_age=settings.refresh_token_expire_days * 86400,
    )
    return TokenResponse(access_token=access_token, expires_in=settings.access_token_expire_minutes * 60)
```

### Solo-Modus
Im Solo-Modus (`HIVEMIND_MODE=solo` oder `app_settings.mode='solo'`):
- `get_current_actor()` gibt automatisch den System-User `solo` zurück ohne Token-Prüfung
- Kein Login nötig — Auth-Middleware prüft Modus und überspringt Token-Validierung
