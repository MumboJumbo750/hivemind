"""Unit-Tests für RBAC-Dependencies (TASK-2-004)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.routers.deps import require_project_access
from app.schemas.auth import CurrentActor


def _make_actor(role: str = "developer") -> CurrentActor:
    return CurrentActor(id=uuid.uuid4(), username="tester", role=role)


@pytest.mark.asyncio
async def test_admin_bypasses_project_check() -> None:
    actor = _make_actor("admin")
    db = AsyncMock()
    result = await require_project_access(uuid.uuid4(), actor, db)
    assert result.role == "admin"
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_developer_in_project_gets_access() -> None:
    actor = _make_actor("developer")
    project_id = uuid.uuid4()

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = MagicMock()  # member vorhanden
    db.execute.return_value = execute_result

    result = await require_project_access(project_id, actor, db)
    assert result.id == actor.id


@pytest.mark.asyncio
async def test_developer_not_in_project_raises_403() -> None:
    actor = _make_actor("developer")
    project_id = uuid.uuid4()

    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None  # kein Member
    db.execute.return_value = execute_result

    with pytest.raises(HTTPException) as exc:
        await require_project_access(project_id, actor, db)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_solo_mode_actor_passes_all_checks() -> None:
    """Solo-Actor hat Admin-Rolle → RBAC übersprungen."""
    actor = CurrentActor(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        username="solo",
        role="admin",
    )
    db = AsyncMock()
    result = await require_project_access(uuid.uuid4(), actor, db)
    assert result.username == "solo"
