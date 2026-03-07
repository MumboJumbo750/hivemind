from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic_proposal import EpicProposal
from app.models.sync import SyncOutbox

TASK_KEY_RE = re.compile(r"\bTASK-[A-Z0-9-]+\b")
EPIC_KEY_RE = re.compile(r"\bEPIC-[A-Z0-9-]+\b")


class IntakeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def prepare_requirement_capture(
        self,
        *,
        project_id: uuid.UUID,
        text: str,
    ) -> dict[str, Any]:
        existing = await self._find_existing_requirement(project_id, text)
        refs = self._extract_context_refs({"text": text})
        if existing is None:
            return {
                "existing_draft": None,
                "intake": {
                    "stage": "captured",
                    "source_kind": "requirement",
                    "materialization": "proposal_draft",
                    "project_id": str(project_id),
                    "triage_required": False,
                    "context_refs": refs,
                },
            }

        materialization = "existing_draft" if existing.state == "draft" else "existing_proposal"
        return {
            "existing_draft": existing,
            "intake": {
                "stage": "captured",
                "source_kind": "requirement",
                "materialization": materialization,
                "project_id": str(project_id),
                "triage_required": False,
                "context_refs": refs,
                "existing_proposal_id": str(existing.id),
            },
        }

    def build_inbound_capture(
        self,
        *,
        source_kind: str,
        project_context: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        matched = bool(project_context.get("project_id"))
        materialization = "bug_report" if source_kind == "sentry_event" and matched else "triage_event"
        return {
            "stage": "captured",
            "source_kind": source_kind,
            "materialization": materialization,
            "project_id": project_context.get("project_id"),
            "project_slug": project_context.get("project_slug"),
            "triage_required": not matched or source_kind != "sentry_event",
            "context_refs": self._extract_context_refs(payload),
        }

    def resolve_inbound_outcome(self, entry: SyncOutbox) -> dict[str, Any]:
        payload = dict(entry.payload or {})
        refs = self._extract_context_refs(payload)

        if entry.system == "sentry":
            return self._outcome(
                routing_state="routed",
                intake_stage="materialized",
                materialization="bug_report",
                refs=refs,
                reason=None,
            )

        if not entry.project_id:
            return self._outcome(
                routing_state="unrouted",
                intake_stage="triage_pending",
                materialization="triage_event",
                refs=refs,
                reason="missing project context",
            )

        if refs["task_keys"] or refs["epic_keys"]:
            return self._outcome(
                routing_state="unrouted",
                intake_stage="triage_pending",
                materialization="existing_context_reference",
                refs=refs,
                reason="manual triage required for referenced task/epic",
            )

        return self._outcome(
            routing_state="unrouted",
            intake_stage="triage_pending",
            materialization="triage_event",
            refs=refs,
            reason=f"{entry.system} inbound has no direct materializer",
        )

    def apply_inbound_outcome(self, entry: SyncOutbox, outcome: dict[str, Any]) -> None:
        payload = dict(entry.payload or {})
        payload["_intake"] = {
            **dict(payload.get("_intake") or {}),
            "stage": outcome["intake_stage"],
            "materialization": outcome["materialization"],
            "context_refs": outcome["context_refs"],
            "triage_required": outcome["routing_state"] == "unrouted",
        }
        entry.payload = payload
        detail = dict(entry.routing_detail or {})
        detail["intake_stage"] = outcome["intake_stage"]
        detail["materialization"] = outcome["materialization"]
        if outcome.get("reason"):
            detail["reason"] = outcome["reason"]
        entry.routing_detail = detail
        entry.routing_state = outcome["routing_state"]

    async def _find_existing_requirement(
        self,
        project_id: uuid.UUID,
        text: str,
    ) -> EpicProposal | None:
        result = await self.db.execute(
            select(EpicProposal).where(
                EpicProposal.project_id == project_id,
                EpicProposal.state.in_(("draft", "proposed")),
                or_(
                    EpicProposal.raw_requirement == text,
                    EpicProposal.description == text,
                ),
            )
        )
        return result.scalars().first()

    def _extract_context_refs(self, payload: dict[str, Any]) -> dict[str, list[str]]:
        parts: list[str] = []
        for key in ("text", "summary", "title", "message", "description", "external_id"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                parts.append(value)
        joined = "\n".join(parts)
        return {
            "task_keys": sorted(set(TASK_KEY_RE.findall(joined))),
            "epic_keys": sorted(set(EPIC_KEY_RE.findall(joined))),
        }

    def _outcome(
        self,
        *,
        routing_state: str,
        intake_stage: str,
        materialization: str,
        refs: dict[str, list[str]],
        reason: str | None,
    ) -> dict[str, Any]:
        return {
            "routing_state": routing_state,
            "intake_stage": intake_stage,
            "materialization": materialization,
            "context_refs": refs,
            "reason": reason,
        }
