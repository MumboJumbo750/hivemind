"""Webhook Ingest — TASK-3-011, TASK-8-009, TASK-8-010.

Endpoints:
  POST /api/webhooks/youtrack       — Receive YouTrack issue events
  POST /api/webhooks/sentry         — Receive Sentry error events
  POST /api/webhooks/gitlab         — Receive GitLab events (TASK-8-009)
  POST /api/webhooks/github         — Receive GitHub events (TASK-8-010)
  POST /api/webhooks/ingest/<token> — Generic ingest endpoint (TASK-8-009)

Security: HMAC-SHA256 signature validation / token header validation.
Storage:  sync_outbox with direction='inbound', routing_state='unrouted'.
"""
import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, Path, Request, status
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

def _verify_token(expected: str, actual: str | None) -> None:
    """Verify a plain token header. Raises 401 on failure."""
    if not expected:
        return  # no secret configured → skip validation
    if not actual or not hmac.compare_digest(expected, actual):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )


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


def _normalize_gitlab(raw: dict, event_type: str) -> dict:
    """Normalize a GitLab webhook payload to internal format."""
    object_attrs = raw.get("object_attributes") or {}
    project = raw.get("project") or {}
    user = raw.get("user") or {}

    # Determine external_id based on event type
    if event_type == "push":
        external_id = raw.get("after") or raw.get("checkout_sha")
        summary = f"Push to {raw.get('ref', '')} by {raw.get('user_name', '')}"
        url = project.get("web_url")
        author = raw.get("user_name")
        timestamp = raw.get("commits", [{}])[0].get("timestamp") if raw.get("commits") else None
    else:
        external_id = str(object_attrs.get("iid") or object_attrs.get("id") or raw.get("object_attributes", {}).get("id", ""))
        summary = object_attrs.get("title") or object_attrs.get("description") or object_attrs.get("ref")
        url = object_attrs.get("url")
        author = user.get("username") or user.get("name")
        timestamp = object_attrs.get("updated_at") or object_attrs.get("created_at")

    return {
        "source": "gitlab",
        "event_type": event_type,
        "external_id": external_id,
        "summary": summary,
        "url": url,
        "author": author,
        "timestamp": timestamp,
        "project": project.get("name") or project.get("path_with_namespace"),
        "project_url": project.get("web_url"),
    }


def _gitlab_entity_type(event_type: str, raw: dict) -> str:
    """Map GitLab X-Gitlab-Event value to internal entity_type."""
    object_attrs = raw.get("object_attributes") or {}
    action = object_attrs.get("action") or object_attrs.get("state") or ""

    if event_type in ("Issue Hook", "Confidential Issue Hook"):
        if action in ("open", "reopen"):
            return "gitlab_issue"
    if event_type == "Merge Request Hook":
        if action == "merge":
            return "gitlab_mr"
    if event_type == "Pipeline Hook":
        if object_attrs.get("status") == "failed":
            return "gitlab_pipeline_failure"
    if event_type == "Push Hook":
        return "gitlab_push"

    # Catch-all: strip " Hook" suffix and lowercase
    slug = event_type.lower().replace(" hook", "").replace(" ", "_")
    return f"gitlab_{slug}"


def _normalize_github(raw: dict, event_type: str) -> dict:
    """Normalize a GitHub webhook payload to internal format."""
    repo = raw.get("repository") or {}
    sender = raw.get("sender") or {}
    action = raw.get("action")

    if event_type == "issues":
        issue = raw.get("issue") or {}
        external_id = str(issue.get("number", ""))
        summary = issue.get("title")
        url = issue.get("html_url")
        timestamp = issue.get("updated_at") or issue.get("created_at")
    elif event_type == "pull_request":
        pr = raw.get("pull_request") or {}
        external_id = str(pr.get("number", ""))
        summary = pr.get("title")
        url = pr.get("html_url")
        timestamp = pr.get("updated_at") or pr.get("created_at")
    elif event_type == "check_run":
        check = raw.get("check_run") or {}
        external_id = str(check.get("id", ""))
        summary = check.get("name")
        url = check.get("html_url") or check.get("details_url")
        timestamp = check.get("completed_at") or check.get("started_at")
    elif event_type == "push":
        external_id = raw.get("after") or raw.get("head_commit", {}).get("id", "")
        summary = f"Push to {raw.get('ref', '')}"
        url = raw.get("compare")
        timestamp = raw.get("head_commit", {}).get("timestamp")
    elif event_type == "workflow_run":
        wf = raw.get("workflow_run") or {}
        external_id = str(wf.get("id", ""))
        summary = wf.get("name") or wf.get("display_title")
        url = wf.get("html_url")
        timestamp = wf.get("updated_at") or wf.get("created_at")
    elif event_type == "projects_v2_item":
        item = raw.get("projects_v2_item") or {}
        external_id = str(item.get("id", ""))
        summary = f"Project item {item.get('content_type', '')} updated"
        url = None
        timestamp = item.get("updated_at")
    elif event_type == "release":
        rel = raw.get("release") or {}
        external_id = str(rel.get("id", ""))
        summary = rel.get("name") or rel.get("tag_name")
        url = rel.get("html_url")
        timestamp = rel.get("published_at") or rel.get("created_at")
    else:
        external_id = str(raw.get("id", ""))
        summary = str(event_type)
        url = None
        timestamp = None

    return {
        "source": "github",
        "event_type": event_type,
        "action": action,
        "external_id": external_id,
        "summary": summary,
        "url": url,
        "repo": repo.get("full_name") or repo.get("name"),
        "sender": sender.get("login"),
        "timestamp": timestamp,
    }


def _github_entity_type(event_type: str, raw: dict) -> str:
    """Map GitHub X-GitHub-Event value and payload action to internal entity_type."""
    action = raw.get("action")

    if event_type == "issues" and action in ("opened", "reopened"):
        return "github_issue"
    if event_type == "pull_request":
        if action == "opened":
            return "github_pr"
        pr = raw.get("pull_request") or {}
        if action == "closed" and pr.get("merged"):
            return "github_pr_merged"
    if event_type == "check_run":
        check = raw.get("check_run") or {}
        if check.get("conclusion") == "failure":
            return "github_check_failure"
    if event_type == "push":
        return "github_push"
    if event_type == "workflow_run":
        wf = raw.get("workflow_run") or {}
        if wf.get("conclusion") == "completed":
            return "github_workflow"
    if event_type == "projects_v2_item" and action == "edited":
        return "github_project_item"
    if event_type == "release" and action == "published":
        return "github_release"

    # Catch-all
    return f"github_{event_type}"


# ── Normalizer registry (used by generic ingest) ───────────────────────────

_NORMALIZERS = {
    "youtrack": _normalize_youtrack,
    "sentry": _normalize_sentry,
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


@router.post("/gitlab", status_code=status.HTTP_202_ACCEPTED)
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str | None = Header(None),
    x_gitlab_event: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Receive a GitLab webhook event (TASK-8-009)."""
    body_bytes = await request.body()

    # 1. Token validation
    _verify_token(settings.hivemind_gitlab_webhook_secret, x_gitlab_token)

    # 2. Parse payload
    raw = json.loads(body_bytes)

    # 3. Determine event type slug
    event_type = (x_gitlab_event or raw.get("event_type") or raw.get("event_name") or "unknown").strip()

    # 4. Determine entity_type and extract external_id
    entity_type = _gitlab_entity_type(event_type, raw)
    normalized = _normalize_gitlab(raw, event_type)
    external_id = normalized.get("external_id") or str(uuid.uuid4())

    # 5. Build dedup key
    dedup_key = f"gitlab:{event_type}:{external_id}"

    # 6. Idempotency check
    existing = await _check_idempotency(db, dedup_key)
    if existing:
        return {"status": "duplicate", "id": str(existing.id)}

    # 7. Store
    entry = SyncOutbox(
        dedup_key=dedup_key,
        direction="inbound",
        system="gitlab",
        entity_type=entity_type,
        entity_id=str(external_id),
        payload=normalized,
        raw_payload=raw,
        routing_state="unrouted",
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    await db.commit()

    await write_audit(
        tool_name="webhook_gitlab",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        actor_role="system",
        input_payload={"dedup_key": dedup_key, "event_type": event_type},
        target_id=str(entry.id),
    )

    return {"status": "accepted", "id": str(entry.id)}


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Receive a GitHub webhook event (TASK-8-010)."""
    body_bytes = await request.body()

    # 1. HMAC-SHA256 validation
    _verify_hmac(
        settings.hivemind_github_webhook_secret,
        body_bytes,
        x_hub_signature_256,
    )

    # 2. Parse payload
    raw = json.loads(body_bytes)

    # 3. Determine event type and delivery id
    event_type = (x_github_event or raw.get("action") or "unknown").strip()
    delivery_id = x_github_delivery or str(uuid.uuid4())

    # 4. Determine entity_type and normalize
    entity_type = _github_entity_type(event_type, raw)
    normalized = _normalize_github(raw, event_type)

    # 5. Build dedup key
    dedup_key = f"github:{event_type}:{delivery_id}"

    # 6. Idempotency check
    existing = await _check_idempotency(db, dedup_key)
    if existing:
        return {"status": "duplicate", "id": str(existing.id)}

    # 7. Store
    external_id = normalized.get("external_id") or delivery_id
    entry = SyncOutbox(
        dedup_key=dedup_key,
        direction="inbound",
        system="github",
        entity_type=entity_type,
        entity_id=str(external_id),
        payload=normalized,
        raw_payload=raw,
        routing_state="unrouted",
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    await db.commit()

    await write_audit(
        tool_name="webhook_github",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        actor_role="system",
        input_payload={"dedup_key": dedup_key, "event_type": event_type},
        target_id=str(entry.id),
    )

    return {"status": "accepted", "id": str(entry.id)}


@router.post("/ingest/{token}", status_code=status.HTTP_202_ACCEPTED)
async def generic_ingest_webhook(
    request: Request,
    token: str = Path(..., description="Ingest token for authentication"),
    db: AsyncSession = Depends(get_db),
):
    """Generic ingest endpoint that routes to the correct normalizer based on 'source' field (TASK-8-009)."""
    body_bytes = await request.body()

    # 1. Parse payload first (source needed for routing)
    raw = json.loads(body_bytes)
    source = str(raw.get("source") or "").lower().strip()

    # 2. Validate token against configured secret for the detected source
    #    Generic ingest uses hivemind_mcp_api_key as the shared ingest token
    _verify_token(settings.hivemind_mcp_api_key, token)

    # 3. Normalize using source-specific normalizer (fall back to passthrough)
    normalizer = _NORMALIZERS.get(source)
    if normalizer:
        normalized = normalizer(raw)
        system = source
    else:
        normalized = {"source": source, "raw": raw}
        system = source or "generic"

    # 4. Derive external_id and dedup key
    external_id = (
        normalized.get("external_id")
        or raw.get("id")
        or raw.get("external_id")
        or str(uuid.uuid4())
    )
    timestamp = normalized.get("timestamp") or raw.get("timestamp") or ""
    dedup_key = f"ingest:{source}:{external_id}:{timestamp}"

    # 5. Idempotency check
    existing = await _check_idempotency(db, dedup_key)
    if existing:
        return {"status": "duplicate", "id": str(existing.id)}

    # 6. Store
    entry = SyncOutbox(
        dedup_key=dedup_key,
        direction="inbound",
        system=system,
        entity_type=f"{system}_event",
        entity_id=str(external_id),
        payload=normalized,
        raw_payload=raw,
        routing_state="unrouted",
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    await db.commit()

    await write_audit(
        tool_name="webhook_ingest",
        actor_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        actor_role="system",
        input_payload={"dedup_key": dedup_key, "source": source},
        target_id=str(entry.id),
    )

    return {"status": "accepted", "id": str(entry.id)}
