"""Unit-Tests for Skill Fork Endpoint (TASK-F-007)."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_fork_creates_local_draft():
    """Fork creates a new local draft skill with parent link."""
    from app.routers.skills import fork_skill

    skill_id = uuid.uuid4()
    own_node_id = uuid.uuid4()

    source = MagicMock()
    source.id = skill_id
    source.title = "FastAPI Auth"
    source.content = "# Auth content"
    source.service_scope = ["backend"]
    source.stack = ["fastapi"]
    source.skill_type = "domain"
    source.federation_scope = "federated"

    identity = MagicMock()
    identity.node_id = own_node_id

    db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = source  # skill lookup
        elif call_count == 2:
            r.scalar_one_or_none.return_value = None  # no existing fork
        elif call_count == 3:
            r.scalar_one_or_none.return_value = identity  # node identity
        return r

    db.execute.side_effect = _execute

    async def _refresh(obj, *args, **kwargs):
        if not hasattr(obj, "id") or obj.id is None:
            obj.id = uuid.uuid4()

    db.refresh.side_effect = _refresh

    resp = await fork_skill(skill_id, db)

    assert resp.created is True
    assert resp.federation_scope == "local"
    assert db.add.call_count == 2  # Skill + SkillParent

    forked_skill = db.add.call_args_list[0][0][0]
    assert forked_skill.title == "FastAPI Auth (Fork)"
    assert forked_skill.lifecycle == "draft"
    assert forked_skill.federation_scope == "local"


@pytest.mark.asyncio
async def test_fork_404_for_missing_skill():
    """Fork returns 404 when skill doesn't exist."""
    from fastapi import HTTPException

    from app.routers.skills import fork_skill

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = None
    db.execute.return_value = r

    with pytest.raises(HTTPException) as exc_info:
        await fork_skill(uuid.uuid4(), db)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_fork_400_for_non_federated():
    """Fork returns 400 when skill is not federated."""
    from fastapi import HTTPException

    from app.routers.skills import fork_skill

    skill = MagicMock()
    skill.federation_scope = "local"

    db = AsyncMock()
    r = MagicMock()
    r.scalar_one_or_none.return_value = skill
    db.execute.return_value = r

    with pytest.raises(HTTPException) as exc_info:
        await fork_skill(uuid.uuid4(), db)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fork_409_for_duplicate():
    """Fork returns 409 when fork already exists."""
    from fastapi import HTTPException

    from app.routers.skills import fork_skill

    skill = MagicMock()
    skill.federation_scope = "federated"
    existing_parent = MagicMock()

    db = AsyncMock()
    call_count = 0

    def _execute(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        r = MagicMock()
        if call_count == 1:
            r.scalar_one_or_none.return_value = skill
        elif call_count == 2:
            r.scalar_one_or_none.return_value = existing_parent  # fork exists
        return r

    db.execute.side_effect = _execute

    with pytest.raises(HTTPException) as exc_info:
        await fork_skill(uuid.uuid4(), db)
    assert exc_info.value.status_code == 409
