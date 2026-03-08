"""Structured learning capture for agent-loop outputs."""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.epic import Epic
from app.models.learning_artifact import LearningArtifact
from app.models.prompt_history import PromptHistory
from app.models.task import Task


from app.services.learning_quality import (
    assess_risk_level,
    classify_review_path,
    should_flag_conflict,
    validate_learning_quality,
)


MIN_CONFIDENCE_BY_TYPE: dict[str, float] = {
    "agent_output": 0.55,
    "review_feedback": 0.65,
    "governance_recommendation": 0.60,
    "execution_learning": 0.70,
}


def build_learning_fingerprint(
    *,
    artifact_type: str,
    source_type: str,
    source_ref: str,
    summary: str,
    dedupe_key: str | None = None,
) -> str:
    raw = "|".join([artifact_type, source_type, dedupe_key or source_ref, summary.strip()])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_learning_status(
    *,
    artifact_type: str,
    confidence: float | None,
    requested_status: str | None = None,
    source_type: str | None = None,
    risk_level: str | None = None,
) -> str:
    """Bestimmt den Status eines Lernartefakts.

    Wenn source_type und risk_level angegeben, wird classify_review_path()
    für eine qualitätsbewusste Pfadentscheidung genutzt.
    Hochrisiko-Artefakte werden nie direkt auf 'accepted' gesetzt, auch wenn
    requested_status dies anfordert.
    """
    # Explizit angeforderter Status wird respektiert, aber Sicherheits-Override
    # verhindert, dass high-risk Artefakte direkt 'accepted' werden.
    if requested_status:
        if risk_level == "high" and requested_status == "accepted":
            return "proposal"
        return requested_status

    # Neue qualitätsbewusste Pfadentscheidung wenn Kontext vorhanden
    if source_type is not None and risk_level is not None:
        return classify_review_path(
            artifact_type=artifact_type,
            source_type=source_type,
            confidence=confidence,
            risk_level=risk_level,
        )

    # Fallback: bisherige Logik (Rückwärtskompatibilität)
    threshold = MIN_CONFIDENCE_BY_TYPE.get(artifact_type, 0.55)
    if confidence is not None and confidence < threshold:
        return "suppressed"
    if artifact_type in {"governance_recommendation", "review_feedback", "execution_learning"}:
        return "proposal"
    return "observation"


def _normalize_signal_text(text: str) -> str:
    normalized = " ".join((text or "").strip().lower().split())
    for char in ",.;:!?()[]{}\"'`":
        normalized = normalized.replace(char, "")
    return normalized[:240]


def _clip_learning_text(text: str | None, limit: int = 220) -> str:
    cleaned = " ".join((text or "").strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _first_meaningful_line(text: str | None) -> str:
    for line in (text or "").splitlines():
        cleaned = line.strip(" -#*\t")
        if len(cleaned) >= 8:
            return cleaned
    return " ".join((text or "").strip().split())[:220]


def _extract_changed_files(artifacts: list[Any] | None) -> list[str]:
    changed_files: list[str] = []
    for artifact in artifacts or []:
        if not isinstance(artifact, dict):
            continue
        for field in ("path", "file"):
            value = artifact.get(field)
            if isinstance(value, str) and value.strip() and value.strip() not in changed_files:
                changed_files.append(value.strip())
        for field in ("paths", "files"):
            values = artifact.get(field)
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, str) and value.strip() and value.strip() not in changed_files:
                    changed_files.append(value.strip())
    return changed_files[:6]


def _merge_learning_details(current: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(current or {})
    incoming_detail = dict(incoming or {})
    for key, value in incoming_detail.items():
        if key in {"source_task_keys", "source_refs", "audiences"}:
            existing = list(merged.get(key) or [])
            for item in value or []:
                if item not in existing:
                    existing.append(item)
            merged[key] = existing
        elif key == "occurrence_count":
            merged[key] = int(merged.get(key) or 0) + int(value or 0)
        elif key == "effectiveness":
            effect = dict(merged.get("effectiveness") or {})
            incoming_effect = dict(value or {})
            for metric in ("prompt_inclusions", "success_count", "qa_failed_count"):
                effect[metric] = int(effect.get(metric) or 0) + int(incoming_effect.get(metric) or 0)
            for list_key in ("success_task_keys", "qa_failed_task_keys", "prompt_history_ids"):
                existing = list(effect.get(list_key) or [])
                for item in incoming_effect.get(list_key) or []:
                    if item not in existing:
                        existing.append(item)
                effect[list_key] = existing[-20:]
            for scalar_key in ("last_outcome", "last_outcome_at", "last_prompt_at"):
                if incoming_effect.get(scalar_key):
                    effect[scalar_key] = incoming_effect[scalar_key]
            merged["effectiveness"] = effect
        elif value not in (None, "", [], {}):
            merged[key] = value
    return merged


async def create_learning_artifact(
    db: AsyncSession,
    *,
    artifact_type: str,
    source_type: str,
    source_ref: str,
    summary: str,
    detail: dict[str, Any] | None = None,
    agent_role: str | None = None,
    source_dispatch_id: str | None = None,
    project_id: str | None = None,
    epic_id: str | None = None,
    task_id: str | None = None,
    confidence: float | None = None,
    status: str | None = None,
    dedupe_key: str | None = None,
    merge_on_duplicate: bool = False,
) -> LearningArtifact | None:
    cleaned = (summary or "").strip()
    if len(cleaned) < 24:
        return None

    # Qualitätsvalidierung: Source-Attribution und Injection-Schutz
    is_valid, rejection_reason = validate_learning_quality(
        cleaned, source_type, source_ref, confidence, detail
    )
    if not is_valid:
        return None

    # Risikobewertung für qualitätsbewussten Review-Pfad
    risk_level = assess_risk_level(
        artifact_type=artifact_type,
        source_type=source_type,
        confidence=confidence,
        agent_role=agent_role,
    )

    # risk_level im Detail speichern (ohne bestehende Werte zu überschreiben)
    enriched_detail: dict[str, Any] = dict(detail or {})
    if "risk_level" not in enriched_detail:
        enriched_detail["risk_level"] = risk_level

    fingerprint = build_learning_fingerprint(
        artifact_type=artifact_type,
        source_type=source_type,
        source_ref=source_ref,
        summary=cleaned,
        dedupe_key=dedupe_key,
    )
    try:
        existing = (
            await db.execute(
                select(LearningArtifact).where(LearningArtifact.fingerprint == fingerprint)
            )
        ).scalar_one_or_none()
        if existing is not None:
            if merge_on_duplicate:
                # Konflikt markieren statt blind mergen, wenn "accepted" durch
                # Low-Trust-Quelle herausgefordert wird
                merge_payload = dict(enriched_detail)
                if should_flag_conflict(existing.status, source_type):
                    merge_payload["has_conflict"] = True
                    merge_payload["conflict_source"] = source_ref

                existing.detail = _merge_learning_details(existing.detail, merge_payload)
                if confidence is not None:
                    existing.confidence = max(float(existing.confidence or 0.0), float(confidence))
                # Konflikts-Override: accepted + Konflikt → zurück auf proposal
                forced_status = "proposal" if merge_payload.get("has_conflict") else (status or existing.status)
                existing.status = normalize_learning_status(
                    artifact_type=artifact_type,
                    confidence=existing.confidence,
                    requested_status=forced_status,
                    source_type=source_type,
                    risk_level=risk_level,
                )
                await db.flush()
            return existing

        artifact = LearningArtifact(
            id=uuid.uuid4(),
            artifact_type=artifact_type,
            status=normalize_learning_status(
                artifact_type=artifact_type,
                confidence=confidence,
                requested_status=status,
                source_type=source_type,
                risk_level=risk_level,
            ),
            source_type=source_type,
            source_ref=source_ref,
            source_dispatch_id=uuid.UUID(source_dispatch_id) if source_dispatch_id else None,
            agent_role=agent_role,
            project_id=uuid.UUID(project_id) if project_id else None,
            epic_id=uuid.UUID(epic_id) if epic_id else None,
            task_id=uuid.UUID(task_id) if task_id else None,
            summary=cleaned,
            detail=enriched_detail,
            confidence=confidence,
            fingerprint=fingerprint,
        )
        db.add(artifact)
        await db.flush()
        return artifact
    except Exception:
        return None


async def capture_dispatch_learning(
    db: AsyncSession,
    *,
    dispatch_id: str,
    agent_role: str,
    dispatch_context: dict[str, Any] | None,
    content: str | None,
    tool_calls: list[dict[str, Any]] | None,
    status: str,
) -> LearningArtifact | None:
    if status not in {"completed", "partial"}:
        return None
    detail = {
        "tool_calls": tool_calls or [],
        "dispatch_context": dispatch_context or {},
        "status": status,
    }
    return await create_learning_artifact(
        db,
        artifact_type="agent_output",
        source_type="dispatch",
        source_ref=dispatch_id,
        source_dispatch_id=dispatch_id,
        agent_role=agent_role,
        project_id=(dispatch_context or {}).get("project_id"),
        epic_id=(dispatch_context or {}).get("epic_id"),
        task_id=(dispatch_context or {}).get("task_id"),
        summary=(content or "")[:1200],
        detail=detail,
        confidence=0.70 if status == "completed" else 0.58,
    )


async def create_execution_learning_artifacts(
    db: AsyncSession,
    *,
    source_type: str,
    source_ref: str,
    summary: str,
    detail: dict[str, Any] | None = None,
    agent_role: str | None = None,
    project_id: str | None = None,
    epic_id: str | None = None,
    task_id: str | None = None,
) -> list[LearningArtifact]:
    candidates = _build_execution_learning_candidates(
        source_type=source_type,
        source_ref=source_ref,
        summary=summary,
        detail=detail or {},
        agent_role=agent_role,
        project_id=project_id,
    )
    artifacts: list[LearningArtifact] = []
    for candidate in candidates:
        artifact = await create_learning_artifact(
            db,
            artifact_type="execution_learning",
            source_type=source_type,
            source_ref=candidate["source_ref"],
            summary=candidate["summary"],
            detail=candidate["detail"],
            agent_role=agent_role,
            project_id=project_id,
            epic_id=epic_id,
            task_id=task_id,
            confidence=candidate["confidence"],
            dedupe_key=candidate["dedupe_key"],
            merge_on_duplicate=True,
        )
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts


def _build_execution_learning_candidates(
    *,
    source_type: str,
    source_ref: str,
    summary: str,
    detail: dict[str, Any],
    agent_role: str | None,
    project_id: str | None,
) -> list[dict[str, Any]]:
    normalized_project = project_id or "global"
    candidates: list[dict[str, Any]] = []
    excerpt = _clip_learning_text(summary, 220)

    if source_type == "worker_result":
        changed_files = _extract_changed_files(detail.get("artifacts"))
        headline = _first_meaningful_line(summary)
        if headline:
            dedupe_parts = ["worker_result", normalized_project, _normalize_signal_text(headline)]
            if changed_files:
                dedupe_parts.extend(changed_files[:3])
            candidates.append(
                {
                    "source_ref": f"{source_ref}:fix_pattern",
                    "summary": f"Fixmuster: {headline}",
                    "confidence": 0.76 if changed_files else 0.70,
                    "dedupe_key": "|".join(dedupe_parts),
                    "detail": {
                        "kind": "fix_pattern",
                        "audiences": ["worker", "gaertner"],
                        "occurrence_count": 1,
                        "source_refs": [source_ref],
                        "source_task_keys": [detail.get("task_key")] if detail.get("task_key") else [],
                        "changed_files": changed_files,
                        "result_excerpt": excerpt,
                        "effectiveness": {},
                    },
                }
            )

    checklist = detail.get("checklist") or []
    failed_items = []
    for item in checklist:
        if isinstance(item, dict) and item.get("passed") is False:
            label = str(item.get("item") or item.get("criterion") or "").strip()
            if label:
                failed_items.append(label)
    for failed_item in failed_items[:4]:
        candidates.append(
            {
                "source_ref": f"{source_ref}:check:{_normalize_signal_text(failed_item)[:60]}",
                "summary": f"Review-Check: {failed_item}",
                "confidence": 0.84,
                "dedupe_key": "|".join(
                    ["review_checklist", normalized_project, _normalize_signal_text(failed_item)]
                ),
                "detail": {
                    "kind": "review_checklist",
                    "audiences": ["reviewer", "worker"],
                    "occurrence_count": 1,
                    "source_refs": [source_ref],
                    "source_task_keys": [detail.get("task_key")] if detail.get("task_key") else [],
                    "failed_check": failed_item,
                    "review_excerpt": excerpt,
                    "effectiveness": {},
                },
            }
        )

    reject_reason = _first_meaningful_line(summary)
    if source_type in {"task_review_reject", "review_recommendation", "resume_package"} and reject_reason:
        candidates.append(
            {
                "source_ref": f"{source_ref}:reject_reason",
                "summary": f"Reject-Grund: {reject_reason}",
                "confidence": 0.79,
                "dedupe_key": "|".join(
                    ["reject_reason", normalized_project, _normalize_signal_text(reject_reason)]
                ),
                "detail": {
                    "kind": "reject_reason",
                    "audiences": ["worker", "reviewer", "gaertner"],
                    "occurrence_count": 1,
                    "source_refs": [source_ref],
                    "source_task_keys": [detail.get("task_key")] if detail.get("task_key") else [],
                    "review_excerpt": excerpt,
                    "effectiveness": {},
                },
            }
        )
        candidates.append(
            {
                "source_ref": f"{source_ref}:skill_candidate",
                "summary": f"Skill-Kandidat: {reject_reason}",
                "confidence": 0.77,
                "dedupe_key": "|".join(
                    ["skill_candidate", normalized_project, _normalize_signal_text(reject_reason)]
                ),
                "detail": {
                    "kind": "skill_candidate",
                    "audiences": ["gaertner"],
                    "occurrence_count": 1,
                    "source_refs": [source_ref],
                    "source_task_keys": [detail.get("task_key")] if detail.get("task_key") else [],
                    "review_excerpt": excerpt,
                    "effectiveness": {},
                },
            }
        )

    for gap in (detail.get("open_dod_gaps") or [])[:4]:
        criterion = str(gap.get("criterion") or "").strip() if isinstance(gap, dict) else ""
        if not criterion:
            continue
        candidates.append(
            {
                "source_ref": f"{source_ref}:dod_gap:{_normalize_signal_text(criterion)[:60]}",
                "summary": f"Resume-Fokus: DoD-Luecke '{criterion}'",
                "confidence": 0.83,
                "dedupe_key": "|".join(
                    ["resume_dod_gap", normalized_project, _normalize_signal_text(criterion)]
                ),
                "detail": {
                    "kind": "resume_guidance",
                    "audiences": ["worker", "reviewer"],
                    "occurrence_count": 1,
                    "source_refs": [source_ref],
                    "source_task_keys": [detail.get("task_key")] if detail.get("task_key") else [],
                    "dod_gap": criterion,
                    "review_excerpt": excerpt,
                    "effectiveness": {},
                },
            }
        )

    for failure in (detail.get("guard_failures") or [])[:4]:
        title = str(failure.get("title") or "").strip() if isinstance(failure, dict) else ""
        if not title:
            continue
        candidates.append(
            {
                "source_ref": f"{source_ref}:guard:{_normalize_signal_text(title)[:60]}",
                "summary": f"Resume-Fokus: Guard '{title}' erneut pruefen",
                "confidence": 0.81,
                "dedupe_key": "|".join(
                    ["resume_guard", normalized_project, _normalize_signal_text(title)]
                ),
                "detail": {
                    "kind": "resume_guidance",
                    "audiences": ["worker", "reviewer"],
                    "occurrence_count": 1,
                    "source_refs": [source_ref],
                    "source_task_keys": [detail.get("task_key")] if detail.get("task_key") else [],
                    "guard_title": title,
                    "review_excerpt": excerpt,
                    "effectiveness": {},
                },
            }
        )

    return [candidate for candidate in candidates if len(candidate["summary"].strip()) >= 24]


async def get_relevant_execution_learnings(
    db: AsyncSession,
    *,
    task: Task,
    audience: str,
    limit: int = 4,
) -> list[LearningArtifact]:
    epic = (
        await db.execute(select(Epic).where(Epic.id == task.epic_id))
    ).scalar_one_or_none()
    project_id = str(epic.project_id) if epic and epic.project_id else None
    result = await db.execute(
        select(LearningArtifact)
        .where(
            LearningArtifact.artifact_type == "execution_learning",
            LearningArtifact.status != "suppressed",
        )
        .order_by(desc(LearningArtifact.created_at))
        .limit(40)
    )
    artifacts = list(result.scalars().all())

    filtered: list[LearningArtifact] = []
    for artifact in artifacts:
        if artifact.project_id and project_id and str(artifact.project_id) != project_id:
            continue
        detail = dict(artifact.detail or {})
        audiences = set(detail.get("audiences") or [])
        if audiences and audience not in audiences:
            continue
        filtered.append(artifact)

    def _sort_key(artifact: LearningArtifact) -> tuple[int, int, float]:
        detail = dict(artifact.detail or {})
        effect = dict(detail.get("effectiveness") or {})
        helped = int(effect.get("success_count") or 0)
        occurrences = int(detail.get("occurrence_count") or 0)
        confidence = float(artifact.confidence or 0.0)
        return (helped, occurrences, confidence)

    filtered.sort(key=_sort_key, reverse=True)
    return filtered[:limit]


async def record_prompt_learning_context(
    db: AsyncSession,
    *,
    prompt_history: PromptHistory,
    context_refs: list[dict[str, Any]] | None,
) -> None:
    refs = [ref for ref in (context_refs or []) if ref.get("type") == "learning_artifact"]
    if not refs:
        return
    unique_ids: set[str] = set()
    for ref in refs:
        artifact_id = str(ref.get("id") or "").strip()
        if not artifact_id or artifact_id in unique_ids:
            continue
        unique_ids.add(artifact_id)
        artifact = (
            await db.execute(select(LearningArtifact).where(LearningArtifact.id == uuid.UUID(artifact_id)))
        ).scalar_one_or_none()
        if artifact is None:
            continue
        artifact.detail = _merge_learning_details(
            artifact.detail,
            {
                "effectiveness": {
                    "prompt_inclusions": 1,
                    "prompt_history_ids": [str(prompt_history.id)],
                    "last_prompt_at": prompt_history.created_at.isoformat() if prompt_history.created_at else None,
                }
            },
        )
    await db.flush()


async def record_learning_outcome_for_task(
    db: AsyncSession,
    *,
    task: Task,
    outcome: str,
) -> None:
    outcome_at = datetime.now(UTC).isoformat()
    result = await db.execute(
        select(PromptHistory)
        .where(PromptHistory.task_id == task.id)
        .order_by(desc(PromptHistory.created_at))
        .limit(12)
    )
    prompt_entries = list(result.scalars().all())
    unique_ids: set[str] = set()
    for entry in prompt_entries:
        for ref in entry.context_refs or []:
            if isinstance(ref, dict) and ref.get("type") == "learning_artifact":
                artifact_id = str(ref.get("id") or "").strip()
                if artifact_id:
                    unique_ids.add(artifact_id)

    for artifact_id in unique_ids:
        artifact = (
            await db.execute(select(LearningArtifact).where(LearningArtifact.id == uuid.UUID(artifact_id)))
        ).scalar_one_or_none()
        if artifact is None:
            continue
        effect_key = "success_task_keys" if outcome == "success" else "qa_failed_task_keys"
        metric_key = "success_count" if outcome == "success" else "qa_failed_count"
        artifact.detail = _merge_learning_details(
            artifact.detail,
            {
                "effectiveness": {
                    metric_key: 1,
                    effect_key: [task.task_key],
                    "last_outcome": outcome,
                    "last_outcome_at": outcome_at,
                }
            },
        )
    await db.flush()


async def list_execution_learning_artifacts(
    db: AsyncSession,
    *,
    limit: int = 20,
    status: str | None = None,
    audience: str | None = None,
) -> list[LearningArtifact]:
    stmt = (
        select(LearningArtifact)
        .where(LearningArtifact.artifact_type == "execution_learning")
        .order_by(desc(LearningArtifact.created_at))
        .limit(limit)
    )
    if status:
        stmt = stmt.where(LearningArtifact.status == status)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    if not audience:
        return rows
    filtered: list[LearningArtifact] = []
    for row in rows:
        audiences = set(dict(row.detail or {}).get("audiences") or [])
        if not audiences or audience in audiences:
            filtered.append(row)
    return filtered
