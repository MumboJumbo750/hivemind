"""Shared test fixtures — DB isolation & ASGI client.

Sets TESTING=true so lifespan skips bootstrap_node/scheduler.
Provides a `client` fixture that overrides get_current_actor
to return _SOLO_ACTOR directly (no DB call needed in solo mode).
For tests that need real DB access, use the `client_with_db` fixture.
"""
from __future__ import annotations

import os

# Must be set BEFORE any app imports so Settings picks it up
os.environ["TESTING"] = "true"

from collections.abc import AsyncGenerator  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers.deps import get_current_actor  # noqa: E402
from app.schemas.auth import CurrentActor  # noqa: E402

_SOLO_ACTOR = CurrentActor(
    id="00000000-0000-0000-0000-000000000001",
    username="solo",
    role="admin",
)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient that bypasses auth/DB for solo-mode tests.

    Overrides get_current_actor to return _SOLO_ACTOR directly,
    so no DB connection is opened and no event-loop mismatch occurs.
    """

    async def _override_actor() -> CurrentActor:
        return _SOLO_ACTOR

    app.dependency_overrides[get_current_actor] = _override_actor
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
