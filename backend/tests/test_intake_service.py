from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.intake_service import IntakeService


@pytest.mark.asyncio
async def test_prepare_requirement_capture_reuses_existing_draft() -> None:
    proposal_id = uuid.uuid4()
    project_id = uuid.uuid4()
    proposal = SimpleNamespace(id=proposal_id, state="draft")

    result = MagicMock()
    result.scalars.return_value.first.return_value = proposal

    db = AsyncMock()
    db.execute.return_value = result

    svc = IntakeService(db)
    prepared = await svc.prepare_requirement_capture(project_id=project_id, text="Need EPIC-42 support")

    assert prepared["existing_draft"] is proposal
    assert prepared["intake"]["materialization"] == "existing_draft"
    assert prepared["intake"]["context_refs"]["epic_keys"] == ["EPIC-42"]


def test_resolve_inbound_outcome_flags_youtrack_for_triage() -> None:
    db = AsyncMock()
    svc = IntakeService(db)
    entry = SimpleNamespace(
        system="youtrack",
        project_id=uuid.uuid4(),
        payload={"summary": "Update for TASK-123"},
        routing_detail={},
        routing_state="unrouted",
    )

    outcome = svc.resolve_inbound_outcome(entry)

    assert outcome["routing_state"] == "unrouted"
    assert outcome["intake_stage"] == "triage_pending"
    assert outcome["context_refs"]["task_keys"] == ["TASK-123"]
