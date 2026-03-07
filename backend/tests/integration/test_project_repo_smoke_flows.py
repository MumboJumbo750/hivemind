from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.db import AsyncSessionLocal
from app.models.epic_proposal import EpicProposal
from app.models.prompt_history import PromptHistory
from app.models.project import Project
from app.models.project_integration import ProjectIntegration
from app.models.sync import SyncOutbox
from app.services.outbox_consumer import process_inbound

ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio(loop_scope="session")
async def test_requirement_capture_reuses_existing_draft_integration(client) -> None:
    project_id = uuid.uuid4()
    text = f"Implement local repo onboarding flow {uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        db.add(
            Project(
                id=project_id,
                name="Smoke Project",
                slug=f"smoke-project-{uuid.uuid4().hex[:6]}",
                description="integration test",
                created_by=ADMIN_ID,
            )
        )
        await db.commit()

    draft_ids: list[uuid.UUID] = []
    try:
        with patch("app.routers.epic_proposals.write_audit", new=AsyncMock()):
            first = await client.post("/api/epic-proposals/draft-requirement", json={"project_id": str(project_id), "text": text})
            second = await client.post("/api/epic-proposals/draft-requirement", json={"project_id": str(project_id), "text": text})

        assert first.status_code == 200
        assert second.status_code == 200
        payload1 = first.json()
        payload2 = second.json()
        assert payload1["draft_id"] == payload2["draft_id"]
        assert payload2["intake"]["materialization"] == "existing_draft"
        draft_ids.append(uuid.UUID(payload1["draft_id"]))
    finally:
        async with AsyncSessionLocal() as db:
            if draft_ids:
                await db.execute(delete(EpicProposal).where(EpicProposal.id.in_(draft_ids)))
            await db.execute(delete(PromptHistory).where(PromptHistory.project_id == project_id))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_youtrack_webhook_routes_to_project_and_stays_triage_pending(client) -> None:
    project_id = uuid.uuid4()
    integration_id = uuid.uuid4()
    slug = f"yt-smoke-{uuid.uuid4().hex[:6]}"
    event_outbox_id: uuid.UUID | None = None

    async with AsyncSessionLocal() as db:
        db.add(
            Project(
                id=project_id,
                name="YouTrack Smoke",
                slug=slug,
                description="integration test",
                created_by=ADMIN_ID,
            )
        )
        db.add(
            ProjectIntegration(
                id=integration_id,
                project_id=project_id,
                integration_type="youtrack",
                display_name="Smoke YT",
                integration_key=f"{slug}-yt",
                external_project_key="CORE",
                project_selector={"aliases": ["CORE"]},
                sync_enabled=True,
                sync_direction="bidirectional",
            )
        )
        await db.commit()

    payload = {
        "issue": {
            "id": f"YT-{uuid.uuid4().hex[:6]}",
            "summary": "Follow up from YouTrack smoke flow",
            "project": {"shortName": "CORE", "name": "Core"},
        },
        "timestamp": "2026-03-06T20:00:00Z",
    }

    try:
        with patch("app.routers.webhooks.write_audit", new=AsyncMock()):
            response = await client.post("/api/webhooks/youtrack", json=payload)

        assert response.status_code == 202
        event_outbox_id = uuid.UUID(response.json()["id"])

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(select(SyncOutbox).where(SyncOutbox.id == event_outbox_id))
            ).scalar_one()
            assert row.project_id == project_id
            assert row.integration_id == integration_id

        await process_inbound()

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(select(SyncOutbox).where(SyncOutbox.id == event_outbox_id))
            ).scalar_one()
            assert row.routing_state == "unrouted"
            assert row.routing_detail["intake_stage"] == "triage_pending"
            assert row.payload["_intake"]["materialization"] == "triage_event"
    finally:
        async with AsyncSessionLocal() as db:
            if event_outbox_id is not None:
                await db.execute(delete(SyncOutbox).where(SyncOutbox.id == event_outbox_id))
            await db.execute(delete(ProjectIntegration).where(ProjectIntegration.id == integration_id))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.commit()
