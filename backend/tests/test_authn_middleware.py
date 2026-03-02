"""Unit tests for get_current_actor dependency (TASK-2-003)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.routers.deps import get_current_actor
from app.services.auth_service import create_access_token


@pytest.mark.asyncio
async def test_solo_mode_returns_solo_actor() -> None:
    """In solo mode RBAC is bypassed."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)

    with patch("app.routers.deps._get_app_mode", return_value="solo"):
        actor = await get_current_actor(credentials=None, db=db)

    assert actor.username == "solo"
    assert actor.role == "admin"


@pytest.mark.asyncio
async def test_valid_token_returns_actor() -> None:
    """Valid token returns CurrentActor with correct fields."""
    user_id = uuid.uuid4()
    token = create_access_token(str(user_id), "developer")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    db = AsyncMock()
    mock_user = MagicMock()
    mock_user.id = user_id
    mock_user.username = "testuser"
    db.get.return_value = mock_user

    with patch("app.routers.deps._get_app_mode", return_value="team"):
        actor = await get_current_actor(credentials=credentials, db=db)

    assert actor.id == user_id
    assert actor.username == "testuser"
    assert actor.role == "developer"


@pytest.mark.asyncio
async def test_missing_token_raises_401() -> None:
    """No token in team mode returns HTTP 401."""
    db = AsyncMock()

    with patch("app.routers.deps._get_app_mode", return_value="team"):
        with pytest.raises(HTTPException) as exc:
            await get_current_actor(credentials=None, db=db)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token_raises_401() -> None:
    """Invalid token returns HTTP 401."""
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token")
    db = AsyncMock()

    with patch("app.routers.deps._get_app_mode", return_value="team"):
        with pytest.raises(HTTPException) as exc:
            await get_current_actor(credentials=credentials, db=db)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_deleted_user_raises_401() -> None:
    """Valid token but deleted user returns HTTP 401."""
    user_id = uuid.uuid4()
    token = create_access_token(str(user_id), "developer")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    db = AsyncMock()
    db.get.return_value = None

    with patch("app.routers.deps._get_app_mode", return_value="team"):
        with pytest.raises(HTTPException) as exc:
            await get_current_actor(credentials=credentials, db=db)

    assert exc.value.status_code == 401
