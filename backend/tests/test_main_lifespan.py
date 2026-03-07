from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.main import lifespan


class _SessionCtx:
    def __init__(self, db: AsyncMock) -> None:
        self._db = db

    async def __aenter__(self) -> AsyncMock:
        return self._db

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_embedding_worker() -> None:
    db = AsyncMock()
    embedding_service = MagicMock()
    embedding_service.start_worker = AsyncMock()
    embedding_service.stop_worker = AsyncMock()

    with patch("app.main.settings.testing", False), \
         patch("app.main.AsyncSessionLocal", new=lambda: _SessionCtx(db)), \
         patch("app.main.bootstrap_node", new=AsyncMock()), \
         patch("app.main.load_peers", new=AsyncMock()), \
         patch("app.main.start_scheduler") as start_scheduler, \
         patch("app.main.stop_scheduler") as stop_scheduler, \
         patch("app.main.get_embedding_service", return_value=embedding_service):
        async with lifespan(MagicMock()):
            embedding_service.start_worker.assert_awaited_once()
            start_scheduler.assert_called_once()

        embedding_service.stop_worker.assert_awaited_once()
        stop_scheduler.assert_called_once()
