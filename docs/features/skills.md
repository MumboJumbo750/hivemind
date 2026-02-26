# Skills

← [Index](../../masterplan.md)

Skills sind **versionierte, agent-agnostische Instruktionsdokumente** für KI-Agenten — vergleichbar mit System-Prompt-Fragmenten. Sie beschreiben *wie* ein bestimmter Aufgabentyp anzugehen ist. Nicht an einen AI-Client gebunden — funktionieren mit Claude, GPT, Gemini und anderen nativ.

---

## Kompatibilität mit Claude Agent Skills

Hivemind Skills folgen bewusst demselben Grundprinzip wie Claude's eigene Agent Skills — **wir erweitern, wir erfinden nicht neu**:

| | Claude Agent Skills | Hivemind Skills |
| --- | --- | --- |
| Format | Markdown mit strukturiertem Header | Markdown mit YAML-Frontmatter |
| Scope | Rollenverhalten, Tool-Nutzung, Stil | Teamkonventionen, Task-Typ-Anweisungen |
| Portabilität | Claude-spezifisch | Agent-agnostisch (Claude, GPT, Gemini, ...) |
| Versionierung | — | Versioniert, Task-Pinning |
| Lifecycle | — | Draft → Pending Merge → Active → Deprecated |
| Composition | — | `extends` (Stacking, s.u.) |
| Verifikation | — | Guards (executable Checks) |

**Body-Kompatibilität:** Der Markdown-Inhalt eines Hivemind Skills folgt denselben Konventionen die Claude für Agent Skills empfiehlt — klare Rolle, handlungsorientierte Anweisungen, Beispiele, Tool-Referenzen. Ein Hivemind Skill kann direkt als Claude-Skill-Fragment genutzt werden; das Frontmatter wird ignoriert wenn es nicht benötigt wird.

---

## Format (vollständig)

```markdown
---
title: "FastAPI Endpoint erstellen"
extends: []                          # Composition: Parent-Skills (s. Sektion unten)
service_scope: ["backend"]
stack: ["python", "fastapi"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
owner_id: "uuid"
confidence: 0.92
source_epics: ["EPIC-12"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Unit Tests"
    command: "pytest tests/unit/"
---

## Skill: FastAPI Endpoint erstellen

### Rolle
Du erstellst einen neuen FastAPI-Endpoint für das Backend.

### Konventionen
- Router-Dateien liegen in `app/routers/`
- Pydantic v2 für Request/Response-Models
- Dependency Injection via `Depends()`
- Kein Business-Logik im Router — nur HTTP-Layer

### Beispiel
```python
@router.post("/items", response_model=ItemResponse, status_code=201)
async def create_item(body: ItemCreate, db: AsyncSession = Depends(get_db)):
    return await item_service.create(db, body)
```

### Verfügbare Tools

- `hivemind/get_task` — Task-Details laden
- `hivemind/submit_result` — Ergebnis schreiben

```text
(Ende des Skill-Dokuments)
```

- **Frontmatter:** maschinenlesbare Metadaten für Hivemind (Lifecycle, Guards, Composition)
- **Body:** Standard-Markdown — jeder AI-Client versteht es ohne Transformation
- **Keine agent-spezifischen Transformationen** in Phase 1–7 — plain Markdown ist universell

---

## Abgrenzung

| | Skill | Doc | Wiki |
| --- | --- | --- | --- |
| Zielgruppe | KI-Agent | Mensch + KI | Mensch + KI |
| Inhalt | Handlungsanweisung | Architekturdokumentation | Globales Wissen, Runbooks, ADRs |
| Scope | Task-Typ-spezifisch | Epic-spezifisch | Global, projektübergreifend |
| Lifecycle | Draft → Active → Deprecated | Living Document | Versioniert |
| Proposal-Pflicht | Ja (Gaertner-Flow + Admin-Merge) | Nein (update_doc direkt) | Nein (Kartograph direkt) |
| Pinning | Task pinnt auf Version | Immer aktuelle Version | Immer aktuelle Version |

---

## Lifecycle

```text
[Draft] → [Pending Merge] → [Active] → [Deprecated]
                         ↘ [Rejected]
```

| State | Bedeutung | Nächster Schritt |
| --- | --- | --- |
| `draft` | Gaertner hat Proposal erstellt | Proposer reicht via `submit_skill_proposal` zur Review ein |
| `pending_merge` | Admin-Review läuft | Admin merged (`merge_skill`) **oder** rejected (`reject_skill`) |
| `active` | Bibliothekar schlägt vor; Tasks pinnen darauf | Gaertner erstellt Change-Proposal |
| `rejected` | Admin hat Proposal abgelehnt — Gaertner erhält Begründung | Neues Proposal möglich |
| `deprecated` | Nicht mehr vorgeschlagen; lesbar für Audit | — |

---

## Versionierung & Task-Pinning

- Tasks pinnen auf die Skill-Version die zum Zeitpunkt von `link_skill` `active` war (nicht Task-Erstellung)
- Skill-Updates während `in_progress` beeinflussen den laufenden Task **nicht**
- Neue Skill-Verknüpfungen erhalten immer die aktuelle `active`-Version
- `skill_versions` ist **immutable** (append-only, kein Delete, kein Update)
- Deprecated Skills bleiben lesbar für Audit, werden dem Bibliothekar nicht mehr angeboten

> **`skills.version` vs. `skill_versions`:** `skills.version` ist die **aktuelle Versionsnummer** des Skills (wird bei jedem Merge inkrementiert: `skills.version += 1`). `skill_versions` enthält die **vollständige, immutable Versionshistorie** aller vergangenen Inhalte. Source of Truth für die aktuelle Version: `skills.version`. Source of Truth für den Inhalt einer bestimmten Version: `skill_versions WHERE skill_id = X AND version = Y`.

---

## Pflicht-Metadaten

| Feld | Typ | Beschreibung |
| --- | --- | --- |
| `title` | string | Klarer, handlungsorientierter Name |
| `service_scope` | string[] | z.B. `["backend"]`, `["frontend"]`, `["devops"]` |
| `stack` | string[] | z.B. `["python", "fastapi"]` |
| `version_range` | object | Gültige Versionen der Stack-Komponenten |
| `owner_id` | uuid | Verantwortlicher User |
| `confidence` | float 0–1 | Verlässlichkeit des Skills (empirisch) |
| `source_epics` | string[] | Aus welchen Epics der Skill destilliert wurde (`epics.external_id`, z.B. `EPIC-12`) |

---

## Global vs. Projektspezifisch

- `project_id = NULL` → globaler Skill (für alle Projekte sichtbar)
- `project_id = <uuid>` → nur für das spezifische Projekt
- Bibliothekar priorisiert projektspezifische Skills über globale bei gleicher Similarity

---

## Guards an Skills

Skills können eigene **Guards** tragen — ausführbare Checks die bestehen müssen wenn der Skill auf einem Task liegt. Das macht Skills zu vollständigen Arbeitsanweisungen: Instruktion + Verifikation in einem.

```yaml
---
title: "FastAPI Endpoint erstellen"
service_scope: ["backend"]
stack: ["python", "fastapi"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Unit Tests"
    command: "pytest tests/unit/"
---
```

Jeder Task der diesen Skill nutzt, erbt diese Guards automatisch (scope: `skill`). Ergänzt durch Guards auf `global`-, `project`- und `task`-Ebene.

→ Vollständige Guard-Spezifikation: [guards.md](./guards.md)

---

## Skill Composition — Stacking via `extends`

Skills können aufeinander aufbauen. Ein spezialisierter Skill erweitert einen allgemeineren — **Instruktionen werden gestapelt, Basisregeln nicht wiederholt**.

### Hierarchie-Beispiel

```text
review-general              (global)         ← "Immer auf Null-Checks prüfen..."
  └─ review-pr              (global)         ← "+ PR-spezifische Checks: Beschreibung, Labels..."
       └─ review-fastapi    (global)         ← "+ FastAPI: Response Models, Dependency Injection..."
            └─ review-auth  (project-spec.)  ← "+ Auth-spezifisch: Token-Expiry, Scope-Checks..."
```

### Frontmatter `extends`

```yaml
---
title: "FastAPI Endpoint Review"
extends:
  - "uuid-review-general"
  - "uuid-review-pr"
service_scope: ["backend"]
stack: ["python", "fastapi"]
---

## Ergänzungen zu review-general und review-pr

Prüfe zusätzlich:
- Response Models vollständig typisiert?
- Kein Business-Logic im Router?
- Dependency Injection korrekt aufgelöst?
```

Mehrere Parents (Mixins) sind möglich — `review-fastapi-endpoint` erbt sowohl Review-Konventionen als auch FastAPI-Konventionen.

### Assembly durch den Bibliothekar

```text
Bibliothekar lädt "review-fastapi-endpoint":
  1. Löse extends-Chain auf (max. 3 Ebenen)
  2. Prüfe auf Circular References → Fehler wenn gefunden
  3. Assembliere: parent-content → child-content (append)
  4. Token Radar zeigt Breakdown:
     review-general:    180 Tokens
     review-pr:         220 Tokens
     review-fastapi:    160 Tokens  (eigener Inhalt)
     ─────────────────────────────
     Gesamt:            560 Tokens
```

### Regeln

| Regel | Beschreibung |
| --- | --- |
| **Max. 3 Ebenen (Tiefe)** | Backend-Enforcement: `propose_skill` gibt HTTP 422 zurück wenn die aufgelöste `extends`-Kette tiefer als 3 Ebenen ist. Flachen oder aufsplitten ist Pflicht. |
| **Max. 5 Parents (Breite)** | Backend-Enforcement: Die Gesamtsumme aller inkludierten Parent-Skills aus dem Baum darf 5 nicht überschreiten (Token-Budget-Schutz). |
| **Diamond-Auflösung** | Wenn mehrere Parents denselben Ancestor teilen (Diamond), wird der gemeinsame Ancestor **nur einmal** eingefügt — in der Position des ersten Auftretens in der Tiefensuche (DFS, Reihenfolge laut `extends`-Array). Keine Duplikate im assemblierten Inhalt. |
| **Circular Check** | Backend verhindert zirkuläre Abhängigkeiten beim Merge (`propose_skill` schlägt fehl wenn Cycle erkannt) |
| **Version-Pinning** | Task pinnt auf Child-Version; Child pinnt intern auf Parent-Versionen (gespeichert in `skill_versions.parent_versions`) |
| **Guard-Vererbung** | Guards aller Parents werden mit den eigenen Guards zusammengeführt (keine Duplikate bei Diamond) |
| **Append-Semantik** | Child-Inhalt wird hinter Parent-Inhalt gesetzt — bei Diamond-Konflikt gewinnt der erste Parent in `extends`-Reihenfolge |

### Versionierung bei Composition

- Jeder Skill versioniert **seinen eigenen Inhalt** plus die gepinnten Parent-Versionen
- `skill_versions` speichert einen Snapshot des assemblierten Inhalts (vollständig aufgelöst)
- Tasks sehen beim Pinning den **vollständig assemblierten Skill** — kein Runtime-Resolve nötig

### Wann Stacking sinnvoll ist

```text
Sinnvoll:
  review-general → review-pr → review-fastapi → (project: review-auth)
  coding-general → coding-python → coding-fastapi

Nicht sinnvoll:
  Alles in einen Skill packen (kein Stacking nötig)
  Mehr als 3 Ebenen (Zeichen dass der Skill zu komplex ist → aufsplitten)
```

---

## Pflicht-Metadaten (vollständig)

| Feld | Typ | Pflicht | Beschreibung |
| --- | --- | --- | --- |
| `title` | string | ✓ | Klarer, handlungsorientierter Name |
| `extends` | uuid[] | — | Parent-Skills (Composition, max. 3 Ebenen) |
| `service_scope` | string[] | ✓ | z.B. `["backend"]`, `["frontend"]` |
| `stack` | string[] | ✓ | z.B. `["python", "fastapi"]` |
| `version_range` | object | — | Gültige Versionen der Stack-Komponenten |
| `owner_id` | uuid | ✓ | Verantwortlicher User |
| `confidence` | float 0–1 | ✓ | Verlässlichkeit des Skills (empirisch) |
| `source_epics` | string[] | — | Aus welchen Epics der Skill destilliert wurde (`epics.external_id`) |
| `guards` | object[] | — | Executable Checks (→ [guards.md](./guards.md)) |

---

## Task-Pinning via `pinned_skills` JSONB

Tasks speichern ihre gepinnten Skills als JSONB-Array auf `tasks.pinned_skills`:

```json
[
  { "skill_id": "uuid", "version": 2 },
  { "skill_id": "uuid", "version": 1 }
]
```

**Designentscheidung — kein Fremdschlüssel:** `pinned_skills` ist bewusst JSONB statt einer separaten FK-Join-Tabelle. Das ermöglicht exakte Versions-Snapshots ohne DB-Constraint-Komplexität. Da `skill_versions` immutable (append-only) ist, ist Referential Integrity de-facto gegeben. Konsistenz wird auf Applikationsebene beim Pinning sichergestellt: `skill_id` muss existieren und die Version muss `active` sein.

→ Vollständige Begründung: [data-model.md](../architecture/data-model.md#jsonb-schemas)

---

## Prompt-Templates als Skills

Prompt-Generierungs-Templates (→ [Prompt Pipeline](../agents/prompt-pipeline.md)) sind selbst lifecycle-gemanagte Skills. Sie können also verbessert und versioniert werden wie normale Skills — über den gleichen Gaertner-Flow.
