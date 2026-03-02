"""Webhook Ingest — TASK-3-011.

Endpoints:
  POST /api/webhooks/youtrack — Receive YouTrack issue events
  POST /api/webhooks/sentry   — Receive Sentry error events

Security: HMAC-SHA256 signature validation.
Storage:  sync_outbox with direction='inbound', routing_state='unrouted'.
"""
import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models.sync import SyncOutbox
from app.services.audit import write_audit

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ── Helpers ────────────────────────────────────────────────────────────────

def _verify_hmac(secret: str, body: bytes, signature: str | None) -> None:
    """Verify HMAC-SHA256 signature. Raises 401 on failure."""
    if not secret:
        return  # no secret configured → skip validation
    expected = "sha256=" + hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


async def _check_idempotency(db: AsyncSession, dedup_key: str) -> SyncOutbox | None:
    """Return existing outbox entry if dedup_key already exists."""
    result = await db.execute(
        select(SyncOutbox).where(SyncOutbox.dedup_key == dedup_key)
    )
    return result.scalar_one_or_none()


# ── Normalizers ────────────────────────────────────────────────────────────

def _normalize_youtrack(raw: dict) -> dict:
    """Normalize YouTrack webhook payload to internal format."""
    issue = raw.get("issue") or {}
    return {
        "source": "youtrack",
        "external_id": issue.get("id") or issue.get("idReadable"),
        "summary": issue.get("summary"),
        "state": (issue.get("customFields") or [{}])[0].get("value", {}).get("name")
        if issue.get("customFields")
        else None,
        "updated_by": (raw.get("updatedBy") or {}).get("login"),
        "changes": raw.get("fieldChanges") or [],
        "timestamp": raw.get("timestamp"),
    }


def _normalize_sentry(raw: dict) -> dict:
    """Normalize Sentry webhook payload to internal format."""
    data_obj = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    event = data_obj.get("event") if isinstance(data_obj.get("event"), dict) else {}
    issue = data_obj.get("issue") if isinstance(data_obj.get("issue"), dict) else {}

    issue_id = issue.get("id") or issue.get("shortId") or event.get("groupID") or event.get("group_id")
    event_id = event.get("event_id") or event.get("id")

    project_obj = raw.get("project")
    if isinstance(project_obj, dict):
        project = project_obj.get("slug") or project_obj.get("name")
    else:
        project = project_obj

    if not project:
        event_project = event.get("project")
        if isinstance(event_project, dict):
            project = event_project.get("slug") or event_project.get("name")
        elif isinstance(event_project, str):
            project = event_project

    exception = event.get("exception")
    stacktrace = event.get("stacktrace")
    entries = event.get("entries")
    if not exception and isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("type") != "exception":
                continue
            data = entry.get("data")
            if isinstance(data, dict):
                exception = data
                break

    if not stacktrace and isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list) and values and isinstance(values[0], dict):
            stacktrace = values[0].get("stacktrace")

    return {
        "source": "sentry",
        "external_id": issue_id or event_id,
        "issue_id": issue_id,
        "event_id": event_id,
        "summary": issue.get("title") or event.get("title") or event.get("message"),
        "title": issue.get("title") or event.get("title"),
        "message": event.get("message"),
        "culprit": event.get("culprit") or issue.get("culprit"),
        "level": event.get("level") or issue.get("level"),
        "project": project,
        "url": issue.get("web_url") or issue.get("url") or event.get("web_url") or event.get("url"),
        "timestamp": event.get("timestamp") or issue.get("lastSeen") or raw.get("timestamp"),
        "first_seen": issue.get("firstSeen") or issue.get("first_seen"),
        "fingerprint": event.get("fingerprint") or issue.get("fingerprint"),
        "exception": exception,
        "stacktrace": stacktrace,
    }


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/youtrack", status_code=status.HTTP_202_ACCEPTED)
async def youtrack_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Receive a YouTrack webhook event."""
    body_bytes = await request.body()

    # 1. Signature validation
    _verify_hmac(
        settings.hivemind_youtrack_webhook_secret,
        body_bytes,
        x_hub_signature_256,
    )

    # 2. Parse payload
    raw = json.loads(body_bytes)

    # 3. Derive dedup key
    issue = raw.get("issue") or {}
    event_id = issue.get("id") or issue.get("idReadable") or raw.get("timestamp") or str(uuid.uuid4())
    dedup_key = f"youtrack:{event_id}:{raw.get('timestamp', '')}"

    # 4. Idempotency check
    existing = await _check_idempotency(db, dedup_key)
    if existing:
        return {"status": "duplicate", "id": str(existing.id)}

    # 5. Normalize & store
    normalized = _normalize_youtrack(raw)
    entry = SyncOutbox(
        dedup_key=dedup_key,
        direction="inbound",
        system="youtrack",
        entity_type="youtrack_issue_update",
        entity_id=str(normalized.get("external_id") or event_id),
        payload=normalized,
        raw_payload=raw,
        routing_state="unrouted",
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    await db.commit()

    await write_audit(
        tool_name="webhook_youtrack",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        actor_role="system",
        input_payload={"dedup_key": dedup_key},
        target_id=str(entry.id),
    )

    return {"status": "accepted", "id": str(entry.id)}


@router.post("/sentry", status_code=status.HTTP_202_ACCEPTED)
async def sentry_webhook(
    request: Request,
    sentry_hook_signature: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Receive a Sentry webhook event."""
    body_bytes = await request.body()

    # 1. Signature validation
    _verify_hmac(
        settings.hivemind_sentry_webhook_secret,
        body_bytes,
        sentry_hook_signature,
    )

    # 2. Parse payload
    raw = json.loads(body_bytes)

    # 3. Derive dedup key
    data_obj = raw.get("data") or {}
    event = data_obj.get("event") or data_obj.get("issue") or {}
    event_id = event.get("event_id") or event.get("id") or str(uuid.uuid4())
    dedup_key = f"sentry:{event_id}"

    # 4. Idempotency check
    existing = await _check_idempotency(db, dedup_key)
    if existing:
        return {"status": "duplicate", "id": str(existing.id)}

    # 5. Normalize & store
    normalized = _normalize_sentry(raw)
    entry = SyncOutbox(
        dedup_key=dedup_key,
        direction="inbound",
        system="sentry",
        entity_type="sentry_error",
        entity_id=str(normalized.get("external_id") or event_id),
        payload=normalized,
        raw_payload=raw,
        routing_state="unrouted",
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    await db.commit()

    await write_audit(
        tool_name="webhook_sentry",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        actor_role="system",
        input_payload={"dedup_key": dedup_key},
        target_id=str(entry.id),
    )

    return {"status": "accepted", "id": str(entry.id)}
