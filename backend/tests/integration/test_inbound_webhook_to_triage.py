"""Integration test for TASK-7-003 inbound routing flow.

Flow under test:
1) POST /api/webhooks/sentry creates sync_outbox inbound entry (unrouted)
2) process_inbound() consumes the entry
3) entry is marked routed (audit row remains)
4) node_bug_reports row is created
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select, text, update

from app.db import AsyncSessionLocal
from app.models.code_node import CodeNode
from app.models.epic import Epic
from app.models.federation import Node
from app.models.node_bug_report import NodeBugReport
from app.models.sync import SyncOutbox
from app.services.outbox_consumer import process_inbound


@pytest.mark.asyncio(loop_scope="session")
async def test_sentry_webhook_to_inbound_consumer_creates_bug_report_and_routes_event(client, monkeypatch) -> None:
    issue_id = f"SENTRY-E2E-{uuid.uuid4().hex[:10]}"
    event_id = uuid.uuid4().hex
    code_path = f"backend/app/e2e_inbound_{uuid.uuid4().hex[:8]}.py"

    outbox_id: uuid.UUID | None = None
    node_id: uuid.UUID | None = None
    code_node_id: uuid.UUID | None = None
    epic_id: uuid.UUID | None = None
    embedding = [0.01] * 768
    embedding_literal = "[" + ",".join(str(v) for v in embedding) + "]"

    # Ensure stacktrace mapping can resolve a code node and satisfy code_nodes checks.
    async with AsyncSessionLocal() as db:
        node = Node(
            node_name=f"e2e-node-{uuid.uuid4().hex[:8]}",
            node_url=f"http://e2e-{uuid.uuid4().hex[:8]}.local:8000",
        )
        db.add(node)
        await db.flush()
        node_id = node.id

        code_node = CodeNode(
            path=code_path,
            node_type="file",
            label="E2E Inbound Node",
            origin_node_id=node_id,
        )
        db.add(code_node)
        epic = Epic(
            epic_key=f"EPIC-E2E-{uuid.uuid4().hex[:8]}",
            title="E2E inbound auto-routing target",
            origin_node_id=node.id,
        )
        db.add(epic)
        await db.flush()
        epic_id = epic.id

        # Set embedding via raw SQL because the pgvector column is not mapped in ORM.
        await db.execute(
            text(
                "UPDATE epics "
                "SET embedding = (:embedding)::vector, embedding_model = :model "
                "WHERE id = :epic_id"
            ),
            {
                "embedding": embedding_literal,
                "model": "test-mock-embed",
                "epic_id": epic_id,
            },
        )
        await db.commit()
        await db.refresh(code_node)
        code_node_id = code_node.id

    payload = {
        "action": "event.alert",
        "project": {"slug": "core-api"},
        "data": {
            "issue": {
                "id": issue_id,
                "title": "NullPointerException in inbound flow",
                "firstSeen": "2026-03-01T10:00:00Z",
            },
            "event": {
                "event_id": event_id,
                "title": "NullPointerException in inbound flow",
                "message": "object is None",
                "level": "error",
                "exception": {
                    "values": [
                        {
                            "stacktrace": {
                                "frames": [
                                    {"filename": code_path, "function": "handle_event"},
                                ]
                            }
                        }
                    ]
                },
            },
        },
    }

    try:
        # Avoid async background audit task side effects in the test.
        with patch("app.routers.webhooks.write_audit", new=AsyncMock()):
            resp = await client.post("/api/webhooks/sentry", json=payload)

        assert resp.status_code == 202
        body = resp.json()
        outbox_id = uuid.UUID(body["id"])

        # Validate webhook ingest contract before consuming.
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SyncOutbox).where(SyncOutbox.id == outbox_id))
            entry = result.scalar_one()
            assert entry.direction == "inbound"
            assert entry.system == "sentry"
            assert entry.routing_state == "unrouted"
            assert entry.state == "pending"

            # Force this row to be consumed first even if DB has other unrouted entries.
            await db.execute(
                update(SyncOutbox)
                .where(SyncOutbox.id == outbox_id)
                .values(created_at=datetime(1970, 1, 1, tzinfo=UTC))
            )
            await db.commit()

        # Process exactly one inbound row and avoid external embedding calls.
        import app.services.outbox_consumer as outbox_consumer

        monkeypatch.setattr(outbox_consumer, "INBOUND_BATCH_SIZE", 1)
        with patch(
            "app.services.routing_service.EMBEDDING_SVC.embed",
            new=AsyncMock(return_value=embedding),
        ):
            await process_inbound()

        # DoD assertion: inbound audit row remains and is marked as routed.
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(SyncOutbox).where(SyncOutbox.id == outbox_id))
            entry_after = result.scalar_one()
            assert entry_after.routing_state == "routed"
            assert entry_after.state == "pending"

            bug_result = await db.execute(
                select(NodeBugReport).where(NodeBugReport.sentry_issue_id == issue_id)
            )
            bug_report = bug_result.scalar_one_or_none()
            assert bug_report is not None
            assert bug_report.node_id == code_node_id
            assert bug_report.count >= 1
            assert bug_report.epic_id == epic_id
    finally:
        # Keep local dev DB clean when tests run against the shared compose database.
        async with AsyncSessionLocal() as db:
            if outbox_id is not None:
                await db.execute(delete(SyncOutbox).where(SyncOutbox.id == outbox_id))
            await db.execute(delete(NodeBugReport).where(NodeBugReport.sentry_issue_id == issue_id))
            if epic_id is not None:
                await db.execute(delete(Epic).where(Epic.id == epic_id))
            if code_node_id is not None:
                await db.execute(delete(CodeNode).where(CodeNode.id == code_node_id))
            if node_id is not None:
                await db.execute(delete(Node).where(Node.id == node_id))
            await db.commit()
