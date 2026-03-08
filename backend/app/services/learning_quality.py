"""Learning Quality Filter — TASK-AGENT-005.

Qualitäts- und Übernahmeregeln für Lernartefakte im Hivemind-Lern-Loop.

REVIEW-PFADE (Status beim Speichern):
  accepted     — direkt übernommen: confidence >= 0.85, niedriges Risiko,
                 Quelle aus _HIGH_TRUST_SOURCE_TYPES
  proposal     — Review empfohlen: confidence >= 0.70 oder mittleres Risiko
  observation  — Nur beobachtet: niedrige Confidence oder agent_output-Quelle
  suppressed   — Nicht aktiviert: unter Mindestschwelle, Injection-Risiko erkannt
                 oder Quelle fehlt

QUALITÄTSKRITERIEN (Ablehnung wenn verletzt):
  1. summary muss >= 24 Zeichen enthalten
  2. source_ref darf nicht fehlen oder bedeutungslos sein ("unknown", "-", etc.)
  3. Prompt-Injection-Muster in summary → Ablehnung + Log-Warnung

RISIKO-KLASSIFIZIERUNG (gespeichert in detail.risk_level):
  low    — Review/Governance-Quelle mit confidence >= 0.70
  medium — Agent-Output oder worker_result, kein Injection-Indikator
  high   — Injection-Muster erkannt ODER unbekannte Rolle + geringe Confidence

KONFLIKT-ERKENNUNG:
  Wenn ein bestehendes "accepted"-Artefakt von einem neuen Signal aus
  einer Low-Trust-Quelle herausgefordert wird, wird detail.has_conflict = True
  gesetzt, statt blind zu mergen. Das Artefakt bleibt vergleichbar, muss aber
  erneut reviewed werden.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Prompt-Injection-Patterns ─────────────────────────────────────────────────
# Heuristische Muster für adversarielle System-Instruktionen in Agent-Outputs.
# Nicht exhaustiv, aber ausreichend für bekannte Angriffsvektoren.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(an?\s+)?.{1,40}(ai|assistant|model|bot)\b", re.IGNORECASE),
    re.compile(r"\b(disregard|forget|override)\s+(all\s+)?(previous|instructions|rules|context)\b", re.IGNORECASE),
    re.compile(r"\bnew\s+system\s+prompt\b", re.IGNORECASE),
    re.compile(r"\b(human|assistant|system)\s*:\s*\[", re.IGNORECASE),
    re.compile(r"<\s*(system|instructions?|prompt)\s*>", re.IGNORECASE),
    re.compile(r"\bpretend\s+(you\s+are|to\s+be)\b", re.IGNORECASE),
    re.compile(r"\bjailbreak\b", re.IGNORECASE),
    re.compile(r"###\s*INSTRUCTIONS?\s*###", re.IGNORECASE),
    re.compile(r"\bDAN\s+mode\b", re.IGNORECASE),
]


# ── Triviale Inhalts-Patterns ─────────────────────────────────────────────────
# Generische Einzeiler ohne Informationsgehalt.
_TRIVIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^(done|ok|okay|success|completed?|finished?|fixed?|updated?|changed?|modified?)[\s.,!]*$", re.IGNORECASE),
    re.compile(r"^(task|issue|bug|problem)\s+(done|fixed|resolved|closed|completed)[\s.,!]*$", re.IGNORECASE),
    re.compile(r"^(no\s+)?(changes?|updates?|errors?|issues?)\s*(found|detected|needed|required|made)?[\s.,!]*$", re.IGNORECASE),
    re.compile(r"^(see\s+above|as\s+per\s+above|refer\s+to\s+above)[\s.,!]*$", re.IGNORECASE),
]


# ── Vertrauens-Klassifizierung nach Source-Type ───────────────────────────────

#: Quellen, deren Learnings direkt übernommen werden können (status="accepted"),
#: wenn Confidence und Risiko stimmen.
HIGH_TRUST_SOURCE_TYPES: frozenset[str] = frozenset({
    "task_review_reject",
    "review_feedback",
    "review_recommendation",
    "governance_recommendation",
})

#: Quellen, die maximal "proposal" erreichen — nie direkt "accepted".
LOW_TRUST_SOURCE_TYPES: frozenset[str] = frozenset({
    "dispatch",
    "worker_result",
})


# ── Öffentliche API ───────────────────────────────────────────────────────────


def is_injection_risk(summary: str, detail: dict[str, Any] | None = None) -> bool:
    """Gibt True zurück, wenn summary Prompt-Injection-Muster enthält.

    Agent-Outputs sind Quellen, keine Systeminstruktionen. Diese Funktion
    erkennt Versuche, Agenten-Learnings als Instruktionen zu verschleiern.
    """
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(summary):
            logger.warning(
                "Injection-Muster in Learning-Summary erkannt "
                "(pattern=%r, excerpt=%.80s)",
                pattern.pattern,
                summary,
            )
            return True
    return False


def is_trivial_content(summary: str) -> bool:
    """Gibt True zurück, wenn summary zu generisch für ein nützliches Learning ist."""
    stripped = summary.strip()
    if len(stripped) <= 40:
        for pattern in _TRIVIAL_PATTERNS:
            if pattern.match(stripped):
                return True
    # Rein numerische / symbolische Inhalte
    if re.match(r"^[\d\s\-_.,:;!?()\[\]{}\"'`]+$", stripped):
        return True
    return False


def validate_learning_quality(
    summary: str,
    source_type: str,
    source_ref: str,
    confidence: float | None,
    detail: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Validiert ein Lernsignal gegen Qualitätskriterien.

    Gibt zurück:
        (is_valid, rejection_reason) — is_valid=False bedeutet, das Artefakt
        wird nicht gespeichert.

    Ablehnungsgründe:
        "too_short"         — summary < 24 Zeichen
        "missing_source"    — source_ref fehlt oder ist bedeutungslos
        "injection_risk"    — Prompt-Injection-Muster erkannt
    """
    cleaned = (summary or "").strip()

    # 1. Mindestlänge (bereits in create_learning_artifact geprüft, hier als Safety-Net)
    if len(cleaned) < 24:
        return False, "too_short"

    # 2. Source-Attribution erforderlich
    source_clean = (source_ref or "").strip().lower()
    if not source_clean or source_clean in {"unknown", "-", "n/a", "none", "null", ""}:
        return False, "missing_source"

    # 3. Prompt-Injection-Schutz — Artefakt wird abgelehnt, Warnung ins Log
    if is_injection_risk(cleaned, detail):
        return False, "injection_risk"

    return True, None


def assess_risk_level(
    artifact_type: str,
    source_type: str,
    confidence: float | None,
    agent_role: str | None,
) -> str:
    """Klassifiziert das Risiko eines Lernartefakts.

    Gibt zurück: "low", "medium" oder "high"

    high   — agent_output von unbekannter Rolle + niedrige Confidence
    medium — Low-Trust-Quelle (dispatch, worker_result) oder mittlere Confidence
    low    — High-Trust-Quelle (review, governance) mit ausreichender Confidence
    """
    conf = float(confidence or 0.0)
    role = (agent_role or "").lower().strip()

    # Unbekannte Rolle + agent_output + niedrige Confidence → hohes Risiko
    if artifact_type == "agent_output" and (not role or role == "unknown") and conf < 0.60:
        return "high"

    # Niedrig-vertrauenswürdige Agent-Quellen → medium
    if source_type in LOW_TRUST_SOURCE_TYPES:
        return "medium"

    # Hoch-vertrauenswürdige Review/Governance-Quellen mit Mindest-Confidence → niedrig
    if source_type in HIGH_TRUST_SOURCE_TYPES and conf >= 0.70:
        return "low"

    return "medium"


def classify_review_path(
    artifact_type: str,
    source_type: str,
    confidence: float | None,
    risk_level: str,
) -> str:
    """Bestimmt den Review-Pfad für ein neues Lernartefakt.

    Hierarchie:
        accepted    — confidence >= 0.85, risk_level=low, High-Trust-Quelle
        proposal    — confidence >= 0.70 und risk_level in {low, medium}
        observation — niedrige Confidence oder Low-Trust-Quelle
        suppressed  — unter absolutem Minimum oder high risk + sehr niedrig

    Gibt zurück: "accepted", "proposal", "observation" oder "suppressed"
    """
    conf = float(confidence or 0.0)

    # Hohes Risiko → maximal observation, ggf. suppressed
    if risk_level == "high":
        if conf < 0.50:
            return "suppressed"
        return "observation"

    # Absolutes Minimum
    if conf < 0.40:
        return "suppressed"

    # Direkte Übernahme: High-Trust + hohe Confidence + niedriges Risiko
    if (
        risk_level == "low"
        and source_type in HIGH_TRUST_SOURCE_TYPES
        and conf >= 0.85
        and artifact_type in {"execution_learning", "review_feedback", "governance_recommendation"}
    ):
        return "accepted"

    # Proposal: gute Confidence, kein Hochrisiko
    if conf >= 0.70 and risk_level in {"low", "medium"}:
        return "proposal"

    # Alles andere: Beobachtung
    return "observation"


def should_flag_conflict(
    existing_status: str,
    new_source_type: str,
) -> bool:
    """Gibt True zurück, wenn ein Merge als Konflikt markiert werden soll.

    Ein Konflikt entsteht, wenn ein bereits "accepted" Artefakt von einer
    Low-Trust-Quelle herausgefordert wird. Das Artefakt bleibt bestehen,
    aber detail.has_conflict wird gesetzt, damit ein Reviewer es prüfen kann.
    """
    return existing_status == "accepted" and new_source_type in LOW_TRUST_SOURCE_TYPES
