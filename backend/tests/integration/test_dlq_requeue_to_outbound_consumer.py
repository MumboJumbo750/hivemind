"""Integration test for DLQ requeue -> outbound consumer delete flow (TASK-7-019 DoD #4)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select, update

from app.db import AsyncSessionLocal
from app.models.sync import SyncDeadLetter, SyncOutbox
from app.services.outbox_consumer import process_outbound


@pytest.mark.asyncio(loop_scope="session")
async def test_requeued_outbox_entry_is_processed_and_deleted(client, monkeypatch) -> None:
    token = uuid.uuid4().hex[:10]
    source_outbox_id: uuid.UUID | None = None
    dead_letter_id: uuid.UUID | None = None
    requeued_outbox_id: uuid.UUID | None = None

    try:
        async with AsyncSessionLocal() as db:
            source = SyncOutbox(
                dedup_key=f"it-dlq-source-{token}",
                direction="outbound",
                system="youtrack",
                entity_type="youtrack_status_sync",
                entity_id=f"YT-{token}",
                payload={"external_id": f"YT-{token}", "state": "in_progress"},
                raw_payload={},
                attempts=5,
                next_retry_at=None,
                state="dead_letter",
                routing_state="unrouted",
            )
            db.add(source)
            await db.flush()
            source_outbox_id = source.id

            dead_letter = SyncDeadLetter(
                outbox_id=source.id,
                system=source.system,
                entity_type=source.entity_type,
                entity_id=source.entity_id,
                payload=source.payload,
                error="integration-test forced dlq",
            )
            db.add(dead_letter)
            await db.flush()
            dead_letter_id = dead_letter.id
            await db.commit()

        response = await client.post(f"/api/triage/dead-letters/{dead_letter_id}/requeue")
        assert response.status_code == 200
        requeued_outbox_id = uuid.UUID(response.json()["data"]["new_outbox_id"])

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SyncOutbox).where(SyncOutbox.id == requeued_outbox_id))
            requeued = result.scalar_one()
            assert requeued.attempts == 0
            assert requeued.state == "pending"
            assert requeued.direction == "outbound"

            # Ensure our test row is selected first by the consumer.
            await db.execute(
                update(SyncOutbox)
                .where(SyncOutbox.id == requeued_outbox_id)
                .values(created_at=datetime(1970, 1, 1, tzinfo=UTC))
            )
            await db.commit()

        import app.services.outbox_consumer as outbox_consumer

        monkeypatch.setattr(outbox_consumer, "OUTBOUND_BATCH_SIZE", 1)
        with patch("app.services.outbox_consumer._dispatch_outbound", new=AsyncMock()):
            await process_outbound()

        async with AsyncSessionLocal() as db:
            requeued_result = await db.execute(
                select(SyncOutbox).where(SyncOutbox.id == requeued_outbox_id)
            )
            assert requeued_result.scalar_one_or_none() is None

            dead_letter_result = await db.execute(
                select(SyncDeadLetter).where(SyncDeadLetter.id == dead_letter_id)
            )
            dead_letter_after = dead_letter_result.scalar_one()
            assert dead_letter_after.requeued_at is not None
    finally:
        # Cleanup is mandatory because tests use the shared local dev database.
        async with AsyncSessionLocal() as db:
            if dead_letter_id is not None:
                await db.execute(delete(SyncDeadLetter).where(SyncDeadLetter.id == dead_letter_id))
            if requeued_outbox_id is not None:
                await db.execute(delete(SyncOutbox).where(SyncOutbox.id == requeued_outbox_id))
            if source_outbox_id is not None:
                await db.execute(delete(SyncOutbox).where(SyncOutbox.id == source_outbox_id))
            await db.commit()
