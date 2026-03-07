---
title: "Governance-Levels: Abgestufte Automatisierung"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "pydantic"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-8"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Governance-Levels

### Rolle
Du implementierst das Governance-Level-System — konfigurierbare Autonomie-Stufen pro Entscheidungstyp. Nicht alle Entscheidungen sind gleich kritisch: ein Skill-Merge ist weniger riskant als ein neues Epic. Das System erlaubt dem Admin, pro Entscheidungstyp den Automatisierungsgrad zu wählen.

### Kontext
Governance-Levels schließen die 5 Human-Gates im Autonomy Loop:
- Gate 1: Epic-Proposals akzeptieren
- Gate 2: Epic scopen
- Gate 3: Review-Gate (in_review → done)
- Gate 4: Skill-Proposals mergen
- Gate 5: Decision Requests lösen

### Konventionen
- Governance-Service in `app/services/governance_service.py`
- API-Endpoints in `app/routers/settings.py` (erweitert bestehenden Router)
- Governance-Daten in `app_settings.governance` als JSON-Spalte
- Default: Alles `manual` — Admin schaltet Level einzeln hoch
- Kein globaler "Full Auto"-Schalter — bewusste Entscheidung pro Risikokategorie
- Pydantic-Validierung für alle Governance-Inputs

### Die 3 Stufen

| Level | Bedeutung | Mensch-Aufwand |
| --- | --- | --- |
| `manual` | Mensch entscheidet. System unterstützt mit Kontext (wie Phase 1–7) | Voll |
| `assisted` | AI analysiert + empfiehlt. Mensch bestätigt mit 1-Click | Niedrig |
| `auto` | AI entscheidet + führt aus. Mensch wird notifiziert + kann widersprechen | Minimal |

### Ist-Stand der Umsetzung

- `review` hat einen echten `assisted`/`auto`-Unterschied: `auto` setzt Grace Period + spaeteren Auto-Approve, `assisted` nicht.
- Bei `epic_proposal`, `epic_scoping`, `skill_merge`, `decision_request` und `escalation` sind `assisted` und `auto` aktuell beide ein Dispatch-Gate: der Agent wird gestartet, aber der nachgelagerte Abschluss-Flow ist noch nicht separat ausdifferenziert.
- `guard_merge` hat derzeit noch keinen eigenen Conductor-Entscheidungs-Flow; ein aktivierter Guard wird aber sofort auf passende Tasks in `task_guards` materialisiert und ist damit unmittelbar wirksam.
- `manual` bleibt fuer alle Typen der harte Stop fuer AI-Dispatch.

### Die 7 Entscheidungstypen

| Typ | `manual` | `assisted` | `auto` | Default | Risiko |
| --- | --- | --- | --- | --- | --- |
| `review` | Owner reviewed komplett | AI pre-reviewed, 1-Click | Auto-approved (Grace Period) | `manual` | Mittel |
| `epic_proposals` | Admin reviewed in Triage | AI bewertet Qualität, 1-Click | Auto-accept bei Score ≥ Threshold | `manual` | Hoch |
| `epic_scoping` | Owner scopt manuell | Architekt-Vorschlag, 1-Click | Auto-Scope (Kartograph-Coverage ≥ 80%) | `manual` | Mittel |
| `skill_merge` | Admin reviewed | AI prüft Qualität + Duplikate | Auto-Merge nach ≥ 3 Einsätzen | `manual` | Niedrig |
| `guard_merge` | Admin reviewed | AI prüft Allowlist | Auto-Merge (deterministisch) | `manual` | Niedrig |
| `decisions` | Owner entscheidet | AI analysiert Optionen | Auto bei klarer Gewichtung | `manual` | Hoch |
| `escalations` | Admin löst auf | AI schlägt Resolution vor | Auto bei bekanntem Pattern | `manual` | Hoch |

### Datenmodell & Pydantic-Schema

```python
from pydantic import BaseModel, Field
from typing import Literal

GovernanceLevel = Literal["manual", "assisted", "auto"]

class GovernanceConfig(BaseModel):
    review: GovernanceLevel = "manual"
    epic_proposals: GovernanceLevel = "manual"
    epic_scoping: GovernanceLevel = "manual"
    skill_merge: GovernanceLevel = "manual"
    guard_merge: GovernanceLevel = "manual"
    decisions: GovernanceLevel = "manual"
    escalations: GovernanceLevel = "manual"

class GovernanceAutoConfig(BaseModel):
    """Auto-Level-spezifische Parameter."""
    auto_review_threshold: float = Field(default=0.90, ge=0.0, le=1.0)
    auto_review_grace_minutes: int = Field(default=30, ge=5, le=1440)
    epic_proposal_min_score: float = Field(default=0.80, ge=0.0, le=1.0)
    skill_merge_min_uses: int = Field(default=3, ge=1, le=20)
    decision_confidence_advantage: float = Field(default=0.70, ge=0.0, le=1.0)

# Gespeichert in app_settings:
# {
#   "governance": { "review": "manual", "epic_proposals": "manual", ... },
#   "governance_auto": { "auto_review_threshold": 0.90, ... }
# }
```

### Safeguards (Auto-Bedingungen)

Auto-Level ist nie bedingungslos. Jeder Typ hat Safeguards die auf `assisted` zurückfallen:

```python
class GovernanceService:
    async def check_auto_allowed(self, decision_type: str, context: dict) -> bool:
        """Prüft ob Auto-Entscheidung erlaubt ist. False → Fallback auf assisted."""
        match decision_type:
            case "review":
                # Nie auto-reject. Confidence muss >= Threshold sein.
                return (
                    context["recommendation"] != "reject"
                    and context["confidence"] >= self.auto_config.auto_review_threshold
                )
            case "epic_proposals":
                # Kein Duplikat, Rationale vorhanden, depends_on aufgelöst
                return (
                    not context.get("is_duplicate")
                    and context.get("has_rationale")
                    and context.get("depends_on_resolved")
                )
            case "epic_scoping":
                # Kartograph-Coverage >= 80% im relevanten Bereich
                return context.get("coverage", 0) >= 0.80
            case "skill_merge":
                # Skill >= 3x erfolgreich eingesetzt
                return context.get("successful_uses", 0) >= self.auto_config.skill_merge_min_uses
            case "guard_merge":
                # Command auf Allowlist + Syntax-valide
                return context.get("on_allowlist") and context.get("syntax_valid")
            case "decisions":
                # Max 2 Optionen, klare Präferenz >= 70%
                return (
                    context.get("option_count", 0) <= 2
                    and context.get("confidence_advantage", 0) >= self.auto_config.decision_confidence_advantage
                )
            case "escalations":
                # Gleicher Typ >= 2x gleich resolved
                return context.get("pattern_matches", 0) >= 2
        return False

    async def execute_or_recommend(self, decision_type: str, context: dict) -> str:
        """Führt Auto-Entscheidung aus oder erzeugt Assisted-Empfehlung."""
        governance = await self.get_governance_config()
        level = getattr(governance, decision_type, "manual")

        if level == "manual":
            return "manual"  # Prompt Station zeigt Entscheidung

        if level == "auto" and await self.check_auto_allowed(decision_type, context):
            return "auto"  # AI entscheidet + Grace Period

        return "assisted"  # AI empfiehlt, Mensch bestätigt
```

### API-Endpoints

```python
@router.get("/api/settings/governance")
async def get_governance(db: AsyncSession = Depends(get_db)):
    """Gibt aktuelle Governance-Konfiguration zurück."""
    config = await GovernanceService(db).get_governance_config()
    return {"data": config.model_dump()}

@router.put("/api/settings/governance")
async def update_governance(
    body: GovernanceConfig,
    db: AsyncSession = Depends(get_db),
    actor = Depends(require_admin),
):
    """Aktualisiert Governance-Levels. Nur Admin."""
    await GovernanceService(db).update_governance(body)
    await AuditService(db).log(
        actor_id=actor.id,
        action="update_governance",
        entity_type="settings",
        entity_id="governance",
        input_snapshot=body.model_dump(),
    )
    return {"data": body.model_dump()}
```

### Sicherheitsprinzipien
- **Review-Gate wird nie entfernt** — `auto` delegiert an AI, aber der Review-Schritt existiert immer
- **Auto-Reject gibt es nicht** — reject-Empfehlung erfordert immer menschliche Bestätigung
- **Grace Period bei Auto-Aktionen** — Owner kann innerhalb des Zeitfensters widersprechen
- **Audit-Trail vollständig** — jede AI-Entscheidung mit Confidence, Rationale und Level geloggt
- **Fallback auf `assisted`** — wenn Auto-Bedingungen nicht erfüllt → Mensch einbeziehen, nie blockieren
- **Eskalation bleibt deterministisch** — SLA-Timer und Backup-Owner-Ketten unverändert

### Wichtige Regeln
- Default ist **immer** `manual` — kein automatisches Hochschalten
- Governance-Änderungen sind Audit-pflichtig (Admin-only)
- Kein globaler "Full Auto"-Button — jeder Typ einzeln konfigurierbar
- Auto-Level erfordert immer: Notification an Owner + Grace Period
- Wenn der Code diese letzte Zeile fuer einen Governance-Typ noch nicht einloest, muss die Skill-/Doku-Beschreibung den Ist-Stand klar benennen statt ein bereits fertiges Auto-Verhalten zu behaupten
