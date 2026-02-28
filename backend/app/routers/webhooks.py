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
    data_obj = raw.get("data") or {}
    event = data_obj.get("event") or data_obj.get("issue") or {}
    return {
        "source": "sentry",
        "external_id": event.get("event_id") or event.get("id"),
        "summary": event.get("title") or event.get("message"),
        "level": event.get("level"),
        "project": (raw.get("project") or event.get("project", {}) or {}).get("slug"),
        "url": event.get("web_url") or event.get("url"),
        "timestamp": event.get("timestamp") or raw.get("timestamp"),
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
