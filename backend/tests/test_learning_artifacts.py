from app.services.learning_artifacts import (
    _build_execution_learning_candidates,
    build_learning_fingerprint,
    normalize_learning_status,
    record_learning_outcome_for_task,
    record_prompt_learning_context,
)
from app.models.learning_artifact import LearningArtifact
from app.models.prompt_history import PromptHistory

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def test_normalize_learning_status_suppresses_low_confidence() -> None:
    assert normalize_learning_status(
        artifact_type="governance_recommendation",
        confidence=0.2,
    ) == "suppressed"


def test_learning_fingerprint_is_stable_for_same_payload() -> None:
    one = build_learning_fingerprint(
        artifact_type="agent_output",
        source_type="dispatch",
        source_ref="dispatch-1",
        summary="Useful structured result",
    )
    two = build_learning_fingerprint(
        artifact_type="agent_output",
        source_type="dispatch",
        source_ref="dispatch-1",
        summary="Useful structured result",
    )
    assert one == two


def test_execution_learning_candidates_include_review_check_and_are_dedupable() -> None:
    candidates = _build_execution_learning_candidates(
        source_type="review_recommendation",
        source_ref="REC-1",
        summary="DoD Testabdeckung fehlt weiterhin",
        detail={
            "task_key": "TASK-1",
            "checklist": [{"item": "Tests aktualisieren", "passed": False}],
        },
        agent_role="reviewer",
        project_id="project-1",
    )

    review_check = next(item for item in candidates if item["detail"]["kind"] == "review_checklist")
    assert review_check["summary"] == "Review-Check: Tests aktualisieren"

    fp_one = build_learning_fingerprint(
        artifact_type="execution_learning",
        source_type="review_recommendation",
        source_ref="REC-1",
        summary=review_check["summary"],
        dedupe_key=review_check["dedupe_key"],
    )
    fp_two = build_learning_fingerprint(
        artifact_type="execution_learning",
        source_type="review_recommendation",
        source_ref="REC-2",
        summary=review_check["summary"],
        dedupe_key=review_check["dedupe_key"],
    )
    assert fp_one == fp_two


@pytest.mark.asyncio
async def test_record_prompt_and_outcome_updates_effectiveness() -> None:
    db = AsyncMock()
    db.flush = AsyncMock()
    artifact = LearningArtifact(
        id=uuid.uuid4(),
        artifact_type="execution_learning",
        status="proposal",
        source_type="worker_result",
        source_ref="TASK-1:v1:fix_pattern",
        summary="Fixmuster: Endpoint und Tests gemeinsam anpassen",
        detail={"kind": "fix_pattern", "audiences": ["worker"], "occurrence_count": 1, "effectiveness": {}},
        confidence=0.8,
        fingerprint="fp-" + uuid.uuid4().hex,
        created_at=datetime.now(UTC),
    )
    prompt_entry = PromptHistory(
        id=uuid.uuid4(),
        task_id=uuid.uuid4(),
        agent_type="worker",
        prompt_type="worker",
        prompt_text="Prompt",
        context_refs=[{"type": "learning_artifact", "id": str(artifact.id)}],
    )
    task = SimpleNamespace(
        id=prompt_entry.task_id,
        task_key="TASK-LEARN-1",
        updated_at=datetime.now(UTC),
    )

    db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: artifact),
        SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [prompt_entry])),
        SimpleNamespace(scalar_one_or_none=lambda: artifact),
    ]

    await record_prompt_learning_context(
        db,
        prompt_history=prompt_entry,
        context_refs=prompt_entry.context_refs,
    )
    await record_learning_outcome_for_task(db, task=task, outcome="success")

    effect = artifact.detail["effectiveness"]
    assert effect["prompt_inclusions"] == 1
    assert effect["success_count"] == 1
