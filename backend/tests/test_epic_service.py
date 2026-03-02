"""Unit tests for EpicService update hooks."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.epic import EpicUpdate
from app.services.epic_service import EpicService


@pytest.mark.asyncio
async def test_update_transition_to_scoped_computes_embedding() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()

    epic = MagicMock()
    epic.id = uuid.uuid4()
    epic.epic_key = "EPIC-42"
    epic.state = "incoming"
    epic.title = "Auth: Login stabilisieren"
    epic.description = "Sentry NullPointer beim Login"
    epic.dod_framework = {"checks": ["error-rate < 1%"]}
    epic.version = 3
    epic.embedding_model = None

    svc = EpicService(db)

    with patch.object(EpicService, "get_by_key", new=AsyncMock(return_value=epic)):
        with patch("app.services.epic_service.EMBEDDING_SVC.embed", new=AsyncMock(return_value=[0.1, 0.2])):
            updated = await svc.update("EPIC-42", EpicUpdate(state="scoped"))

    assert updated.state == "scoped"
    assert updated.version == 4
    db.execute.assert_awaited_once()
    stmt = db.execute.await_args.args[0]
    params = db.execute.await_args.args[1]
    assert "UPDATE epics" in stmt.text
    assert params["id"] == str(epic.id)
    assert params["embedding"] == str([0.1, 0.2])


@pytest.mark.asyncio
async def test_update_scoped_to_scoped_does_not_recompute_embedding() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()

    epic = MagicMock()
    epic.id = uuid.uuid4()
    epic.epic_key = "EPIC-43"
    epic.state = "scoped"
    epic.title = "Existing scoped epic"
    epic.description = None
    epic.dod_framework = None
    epic.version = 1

    svc = EpicService(db)

    with patch.object(EpicService, "get_by_key", new=AsyncMock(return_value=epic)):
        with patch("app.services.epic_service.EMBEDDING_SVC.embed", new=AsyncMock(return_value=[0.1, 0.2])) as embed:
            updated = await svc.update("EPIC-43", EpicUpdate(state="scoped"))

    assert updated.state == "scoped"
    assert updated.version == 2
    embed.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_transition_to_scoped_tolerates_embedding_unavailable() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()

    epic = MagicMock()
    epic.id = uuid.uuid4()
    epic.epic_key = "EPIC-44"
    epic.state = "incoming"
    epic.title = "Epic without embedding provider"
    epic.description = "provider down"
    epic.dod_framework = None
    epic.version = 0

    svc = EpicService(db)

    with patch.object(EpicService, "get_by_key", new=AsyncMock(return_value=epic)):
        with patch("app.services.epic_service.EMBEDDING_SVC.embed", new=AsyncMock(return_value=None)):
            updated = await svc.update("EPIC-44", EpicUpdate(state="scoped"))

    assert updated.state == "scoped"
    assert updated.version == 1
    db.execute.assert_not_awaited()
