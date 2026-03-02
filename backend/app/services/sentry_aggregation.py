"""Sentry aggregation service — TASK-7-005.

Aggregates inbound Sentry webhook events into ``node_bug_reports``.
Uses UPSERT on sentry_issue_id for idempotency; increments count on conflict.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.code_node import CodeNode
from app.models.node_bug_report import NodeBugReport
from app.services import event_bus

if TYPE_CHECKING:
    from app.models.sync import SyncOutbox

logger = logging.getLogger(__name__)
_EVENT_ID_HEX_RE = re.compile(r"^[0-9a-fA-F]{32}$")

_SEVERITY_MAP: dict[str, str] = {
    "fatal": "critical",
    "error": "critical",
    "warning": "warning",
    "info": "info",
    "debug": "info",
}


def _map_severity(sentry_level: str) -> str:
    return _SEVERITY_MAP.get(sentry_level.lower(), "critical")


def _as_non_empty_str(value: Any) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _sentry_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _sentry_issue(payload: dict[str, Any]) -> dict[str, Any]:
    issue = _sentry_data(payload).get("issue")
    return issue if isinstance(issue, dict) else {}


def _sentry_event(payload: dict[str, Any]) -> dict[str, Any]:
    event = _sentry_data(payload).get("event")
    return event if isinstance(event, dict) else {}


def _extract_frames_from_exception(exception: Any) -> list[dict[str, Any]]:
    if not isinstance(exception, dict):
        return []
    values = exception.get("values")
    if not isinstance(values, list) or not values:
        return []
    first = values[0] if isinstance(values[0], dict) else {}
    stacktrace = first.get("stacktrace") if isinstance(first, dict) else {}
    frames = stacktrace.get("frames") if isinstance(stacktrace, dict) else []
    return frames if isinstance(frames, list) else []


def _extract_frames_from_stacktrace(stacktrace: Any) -> list[dict[str, Any]]:
    if not isinstance(stacktrace, dict):
        return []
    frames = stacktrace.get("frames")
    return frames if isinstance(frames, list) else []


def _extract_stack_frames(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[list[dict[str, Any]]] = []

    event = _sentry_event(payload)
    issue = _sentry_issue(payload)

    candidates.append(_extract_frames_from_exception(payload.get("exception")))
    candidates.append(_extract_frames_from_stacktrace(payload.get("stacktrace")))
    candidates.append(_extract_frames_from_exception(event.get("exception")))
    candidates.append(_extract_frames_from_stacktrace(event.get("stacktrace")))
    candidates.append(_extract_frames_from_exception(issue.get("exception")))
    candidates.append(_extract_frames_from_stacktrace(issue.get("stacktrace")))

    entries = event.get("entries")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "exception":
                continue
            data = entry.get("data")
            candidates.append(_extract_frames_from_exception(data))

    for frames in candidates:
        if frames:
            return frames
    return []


def _compute_stack_trace_hash(payload: dict[str, Any]) -> Optional[str]:
    """SHA-256 hash over Sentry fingerprint or first 10 stacktrace frames."""
    event = _sentry_event(payload)
    issue = _sentry_issue(payload)

    fingerprint = payload.get("fingerprint") or event.get("fingerprint") or issue.get("fingerprint")
    if fingerprint:
        raw = json.dumps(fingerprint, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    frames = _extract_stack_frames(payload)

    if not frames:
        return None

    key_frames = frames[:10]
    raw = json.dumps(
        [{"f": f.get("filename"), "fn": f.get("function")} for f in key_frames],
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _extract_frames(payload: dict[str, Any]) -> list[str]:
    """Extract file paths from exception stacktrace frames."""
    frames = _extract_stack_frames(payload)
    seen: set[str] = set()
    extracted: list[str] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        filename = _as_non_empty_str(frame.get("filename"))
        if filename and filename not in seen:
            seen.add(filename)
            extracted.append(filename)
    return extracted


def _extract_sentry_issue_id(payload: dict[str, Any]) -> Optional[str]:
    issue = _sentry_issue(payload)
    event = _sentry_event(payload)

    candidates = [
        issue.get("id"),
        issue.get("shortId"),
        issue.get("issue_id"),
        issue.get("issueId"),
        payload.get("sentry_issue_id"),
        payload.get("issue_id"),
        payload.get("issue"),
        event.get("groupID"),
        event.get("group_id"),
        event.get("issue_id"),
        payload.get("external_id"),
        payload.get("id"),
    ]
    for value in candidates:
        val = _as_non_empty_str(value)
        if not val:
            continue
        if _EVENT_ID_HEX_RE.fullmatch(val):
            continue
        return val
    return None


def _extract_first_seen(payload: dict[str, Any]) -> Optional[datetime]:
    issue = _sentry_issue(payload)
    raw = (
        payload.get("firstSeen")
        or payload.get("first_seen")
        or issue.get("firstSeen")
        or issue.get("first_seen")
    )
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_routing_text(payload: dict[str, Any]) -> str:
    """Build a stable text input for embedding/routing from sentry payload."""
    event = _sentry_event(payload)
    issue = _sentry_issue(payload)

    parts: list[str] = []

    for value in (
        payload.get("summary"),
        payload.get("title"),
        payload.get("message"),
        payload.get("culprit"),
        issue.get("title"),
        issue.get("culprit"),
        event.get("title"),
        event.get("message"),
        event.get("culprit"),
    ):
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    level = payload.get("level") or event.get("level") or issue.get("level")
    if isinstance(level, str) and level.strip():
        parts.append(f"level:{level.strip()}")

    project = payload.get("project")
    if isinstance(project, dict):
        project = project.get("slug") or project.get("name")
    if not project:
        event_project = event.get("project")
        if isinstance(event_project, dict):
            project = event_project.get("slug") or event_project.get("name")
        elif isinstance(event_project, str):
            project = event_project
    if not project:
        raw_project = payload.get("project")
        if isinstance(raw_project, dict):
            project = raw_project.get("slug") or raw_project.get("name")
    if isinstance(project, str) and project.strip():
        parts.append(f"project:{project.strip()}")

    if parts:
        return "\n".join(parts)
    return "sentry error"


class SentryAggregationService:
    """Aggregates Sentry events into node_bug_reports table."""

    async def process_outbound(self, outbox_entry: "SyncOutbox") -> None:
        """Sentry outbound sync is a no-op (Sentry pushes to us, not vice versa)."""
        logger.debug("Sentry outbound entry %s — no action required", outbox_entry.id)

    async def process_sentry_event(self, payload: dict[str, Any]) -> None:
        """Aggregate a Sentry event payload into node_bug_reports."""
        now = datetime.now(UTC)
        sentry_issue_id = _extract_sentry_issue_id(payload)
        stack_trace_hash = _compute_stack_trace_hash(payload)
        first_seen = _extract_first_seen(payload) or now
        nested_level = _sentry_event(payload).get("level") or _sentry_issue(payload).get("level")
        severity = _map_severity(str(payload.get("level") or nested_level or "error"))
        file_paths = _extract_frames(payload)
        upserted_reports: list[NodeBugReport] = []

        async with AsyncSessionLocal() as db:
            if sentry_issue_id:
                report = await self._upsert_by_sentry_issue(
                    db=db,
                    sentry_issue_id=sentry_issue_id,
                    stack_trace_hash=stack_trace_hash,
                    first_seen=first_seen,
                    last_seen=now,
                    severity=severity,
                    raw_payload=payload,
                    file_paths=file_paths,
                )
                if report:
                    upserted_reports.append(report)
            else:
                reports = await self._upsert_by_file_paths(
                    db=db,
                    file_paths=file_paths,
                    stack_trace_hash=stack_trace_hash,
                    first_seen=first_seen,
                    last_seen=now,
                    severity=severity,
                    raw_payload=payload,
                )
                upserted_reports.extend(reports)

            await db.commit()

        if upserted_reports:
            from app.services.routing_service import route_bug_to_epic

            routing_text = _build_routing_text(payload)
            for bug_report_id in {report.id for report in upserted_reports}:
                try:
                    await route_bug_to_epic(bug_report_id, routing_text)
                except Exception as exc:
                    logger.warning("Auto-routing failed for bug %s: %s", bug_report_id, exc)

        for report in upserted_reports:
            event_bus.publish(
                "bug_aggregated",
                {
                    "bug_report_id": str(report.id),
                    "node_id": str(report.node_id) if report.node_id else None,
                    "sentry_issue_id": sentry_issue_id,
                    "severity": severity,
                },
                channel="triage",
            )

    async def _upsert_by_sentry_issue(
        self,
        db: Any,
        sentry_issue_id: str,
        stack_trace_hash: Optional[str],
        first_seen: datetime,
        last_seen: datetime,
        severity: str,
        raw_payload: dict[str, Any],
        file_paths: list[str],
    ) -> Optional[NodeBugReport]:
        """UPSERT a NodeBugReport entry keyed on sentry_issue_id."""
        node_id = await _find_code_node_id(db, file_paths)

        result = await db.execute(
            select(NodeBugReport).where(NodeBugReport.sentry_issue_id == sentry_issue_id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.count += 1
            existing.last_seen = last_seen
            existing.severity = severity
            if stack_trace_hash:
                existing.stack_trace_hash = stack_trace_hash
            if node_id and existing.node_id is None:
                existing.node_id = node_id
            return existing
        else:
            if node_id is None:
                logger.warning(
                    "Skipping Sentry bug aggregation for issue %s: no matching code node in stacktrace",
                    sentry_issue_id,
                )
                return None
            new_report = NodeBugReport(
                node_id=node_id,
                sentry_issue_id=sentry_issue_id,
                stack_trace_hash=stack_trace_hash,
                first_seen=first_seen,
                last_seen=last_seen,
                severity=severity,
                count=1,
                raw_payload=raw_payload,
            )
            db.add(new_report)
            await db.flush()
            return new_report

    async def _upsert_by_file_paths(
        self,
        db: Any,
        file_paths: list[str],
        stack_trace_hash: Optional[str],
        first_seen: datetime,
        last_seen: datetime,
        severity: str,
        raw_payload: dict[str, Any],
    ) -> list[NodeBugReport]:
        """Fallback aggregation matching code_nodes by file path."""
        reports: list[NodeBugReport] = []
        for filepath in file_paths:
            if not filepath:
                continue
            node_id = await _find_code_node_id(db, [filepath])
            if not node_id:
                continue

            result = await db.execute(
                select(NodeBugReport).where(
                    NodeBugReport.node_id == node_id,
                    NodeBugReport.sentry_issue_id.is_(None),
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.count += 1
                existing.last_seen = last_seen
                existing.severity = severity
                if stack_trace_hash and not existing.stack_trace_hash:
                    existing.stack_trace_hash = stack_trace_hash
                reports.append(existing)
            else:
                new_report = NodeBugReport(
                    node_id=node_id,
                    stack_trace_hash=stack_trace_hash,
                    first_seen=first_seen,
                    last_seen=last_seen,
                    severity=severity,
                    count=1,
                    raw_payload=raw_payload,
                )
                db.add(new_report)
                await db.flush()
                reports.append(new_report)

        return reports


async def _find_code_node_id(db: Any, file_paths: list[str]) -> Optional[Any]:
    """Fuzzy-match a file path to a code_node.id."""
    for filepath in file_paths:
        if not filepath:
            continue
        result = await db.execute(
            select(CodeNode.id).where(CodeNode.path.like(f"%{filepath}")).limit(1)
        )
        node_id = result.scalar_one_or_none()
        if node_id:
            return node_id
    return None
