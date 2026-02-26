# Guards — Executable Validierungsregeln

← [Index](../../masterplan.md)

Guards sind die **ausführbare Verifikationsschicht** von Hivemind. Während die Definition of Done deklarativ beschreibt *was* gelten muss ("Unit Tests >= 80%"), liefert ein Guard den konkreten Check der das beweist (`pytest --cov-fail-under=80`).

> DoD sagt: *was* gelten muss.
> Guard prüft: *ob* es gilt — automatisch und reproduzierbar.

---

## Guard-Typen

| Typ | Beschreibung | Beispiel |
| --- | --- | --- |
| `executable` | Shell-Command der mit Exit 0 bestehen muss | `npm run lint`, `ruff check .`, `pytest` |
| `declarative` | Bedingung die das System prüft (strukturiert, kein Command) | `coverage >= 80`, `no open decision_requests` |
| `manual` | Mensch bestätigt explizit — ergänzt DoD, aber eigenständig | "PR von zweiter Person reviewed" |

---

## Skippable-Flag

Guards haben ein `skippable`-Flag (default: `true`):

| `skippable` | Worker-Optionen | Typischer Einsatz |
| --- | --- | --- |
| `true` | `passed`, `failed`, `skipped` (mit Begründung) | Empfohlene Checks, nicht-kritische Qualitäts-Guards |
| `false` | Nur `passed` oder `failed` | Sicherheits-Guards, CI-Pflicht-Checks, Compliance |

Bei `skippable: false` lehnt das Backend `report_guard_result { status: "skipped" }` mit HTTP 422 ab. Der Worker muss den Guard bestehen oder explizit als `failed` melden (was den `in_review`-Übergang blockiert).

---

## Executable Guards — Execution Security

**In Phase 1–7 werden Guards manuell durch den Worker ausgeführt** (kein automatisches Backend-Execution). Der Worker führt den Command im AI-Client oder lokal aus und meldet das Ergebnis via `report_guard_result`.

### Self-Reporting — Designentscheidung und Mitigation

In Phase 1–7 sind Guard-Ergebnisse **self-reported** — das Backend verifiziert den Output nicht automatisch. Das ist eine bewusste BYOAI-Designentscheidung.

**Mitigation:**

| Maßnahme | Beschreibung |
| --- | --- |
| **`result`-Pflichtfeld** | `report_guard_result` erfordert einen nicht-leeren `result`-Text für **alle** Status (`passed`, `failed`, `skipped`) — mindestens die relevante Command-Ausgabe oder Begründung |
| **Owner-Review** | Der Owner sieht im Review Panel die Guard-Ergebnisse inkl. `result`-Text; Guard-Bypass ist für den Reviewer erkennbar (z.B. leerer oder offensichtlich gefälschter Output) |
| **Audit-Trail** | Jeder `report_guard_result`-Call wird in `mcp_invocations` mit vollem Input/Output geloggt |
| **Phase 8** | Bei automatischer Ausführung erzeugt das Backend den `result`-Text — kein self-reporting mehr |

> Guard-Bypass ist in Phase 1–7 technisch möglich, aber nicht ohne sichtbare Spuren: fehlendes oder implausibles `result` fällt beim Owner-Review auf und wird im Audit-Log festgehalten.

**Ab Phase 8 (Autonomy), falls automatische Ausführung eingeführt wird:**

| Sicherheitsaspekt | Anforderung |
| --- | --- |
| **Allowlist** | Nur Commands aus einer konfigurierten Allowlist dürfen ausgeführt werden (`HIVEMIND_GUARD_ALLOWLIST`). Default: `pytest`, `ruff`, `eslint`, `npm run *`, `make *`. Freie Shell-Commands (`rm`, `curl`, `wget`, etc.) sind geblockt. |
| **Timeout** | Jeder Guard-Command läuft maximal `HIVEMIND_GUARD_TIMEOUT` Sekunden (default: 120s). Bei Timeout → automatisch `failed`. |
| **Working Directory** | Ausführung immer im Projekt-Root (konfigurierbar). Kein `cd` außerhalb des Roots. |
| **Resource Limits** | CPU + Memory via cgroup (konfigurierbar, default: 1 CPU, 512 MB). |
| **No Shell Injection** | Commands werden als Array übergeben (nicht als Shell-String) — keine String-Interpolation. |

> In Phase 1–7 liegt die Execution-Verantwortung beim Worker. Das Backend speichert nur das Ergebnis. Keine automatische Command-Ausführung durch Hivemind.

---

## Guard-Scopes

Guards werden hierarchisch vererbt. Ein Task erbt alle Guards seiner Ebene:

```text
global                    — gilt für alle Projekte, alle Tasks
  └─ project              — gilt für alle Tasks in einem Projekt
       └─ skill           — gilt für alle Tasks die diesen Skill nutzen
            └─ task       — explizit an einen Task angehängt (vom Architekten)
```

**Beispiel:**

```text
global:   "no hardcoded secrets" (declarative)
project:  "npm run build" (executable) — Projekt nutzt Node
skill:    "FastAPI Endpoint erstellen" → ruff check, pytest (executable)
task:     TASK-88 → extra Integrations-Test (executable)
```

Wenn TASK-88 den Skill "FastAPI Endpoint erstellen" nutzt, muss er bestehen:

- "no hardcoded secrets" (global)
- "npm run build" (project) ← wenn relevant für scope
- `ruff check .` + `pytest` (skill)
- Integrations-Test (task-spezifisch)

---

## `scope` vs. `service_scope` — Semantik

| Feld | Liegt auf | Bedeutung |
| --- | --- | --- |
| `guards.scope` | Guard-Entität | **Service-Tags** für die der Guard gilt (z.B. `["backend"]`). Ein Guard mit `scope: ["backend"]` wird nur auf Tasks mit Backend-Kontext angewendet. Leeres Array `[]` = gilt für alle Scopes. |
| `skills.service_scope` | Skill-Entität | **Service-Tags** für die der Skill relevant ist. Bibliothekar filtert Skills nach `service_scope` beim Context Assembly. |

Beide Felder nutzen dieselbe Tag-Konvention (`"backend"`, `"frontend"`, `"devops"`) — aber auf unterschiedlichen Entitäten und zu unterschiedlichen Zeitpunkten: `service_scope` beim Skill-Laden, `scope` beim Guard-Vererben.

**Beispiel:** Guard `scope: ["backend"]` wird nicht auf einen reinen Frontend-Task angewendet, auch wenn er global definiert ist.

---

## Workflow-Integration

### Wann Guards relevant sind

Guards werden **vor dem Übergang `in_progress → in_review`** geprüft:

```text
Worker arbeitet an TASK-88
  │
  ├─ Worker: hivemind/get_guards { "task_id": "TASK-88" }
  │   → System liefert alle Guards (global + project + skill + task)
  │
  ├─ Worker führt Guards aus (manuell oder via AI-Client)
  │   → hivemind/report_guard_result { "task_id": "TASK-88",
  │                                    "guard_id": "uuid",
  │                                    "status": "passed",
  │                                    "result": "All 42 tests passed" }
  │
  ├─ Alle Guards passed|skipped → update_task_state → in_review möglich
  │
  └─ Guard failed → Task bleibt in in_progress
                    Worker sieht was genau fehlschlug, korrigiert, führt Guard erneut aus
                    → kein State-Wechsel; qa_failed passiert nur wenn Owner in_review ablehnt
```

### Im Worker-Prompt

Guards werden im Worker-Prompt explizit aufgelistet (→ [Prompt Pipeline](../agents/prompt-pipeline.md)):

```text
### Guards — müssen vor in_review bestehen

[global]    ◌ no hardcoded secrets        — declarative
[project]   ◌ npm run build               — executable
[skill]     ◌ ruff check .                — executable
[skill]     ◌ pytest --cov-fail-under=80  — executable
[task]      ◌ ./tests/integration/auth.sh — executable

Ergebnis melden: hivemind/report_guard_result
```

### Im Review Panel

**Phase 2–4:** Das Review Panel zeigt einen kompakten Guard-Statusblock — alle Guards mit `passed`/`failed`/`skipped` und dem `result`-Text. Provenance-Metadaten (`source`, `checked_at`) werden noch nicht angezeigt.

```text
GUARDS
  ✓ no hardcoded secrets       passed
  ✓ npm run build              passed (exit 0)
  ✓ ruff check .               passed (0 errors)
  ✓ pytest --cov-fail-under=80 passed (coverage: 87%)
  ✗ ./tests/integration/auth.sh FAILED
    → Connection refused: localhost:5432
```

**Ab Phase 5:** Jede Guard-Zeile zeigt zusätzlich Provenance-Metadaten — Quelle (`self-reported | system-executed`) und Zeitstempel (`checked_at`). Das ermöglicht dem Owner einzuschätzen, ob ein Guard-Ergebnis plausibel ist.

```text
GUARDS
  ✓ no hardcoded secrets       passed   [self-reported · vor 3 min]
  ✓ npm run build              passed   [self-reported · vor 3 min]
  ✓ ruff check .               passed   [self-reported · vor 3 min]
  ✓ pytest --cov-fail-under=80 passed   [self-reported · vor 3 min]
```

> **Warum Phase 5?** Self-Reporting ist von Phase 1–7 bewusst toleriert (BYOAI-Designentscheidung). Der Provenance-Marker ist ein Hinweis für den Owner, kein Sicherheitsmechanismus — er wird erst eingeführt wenn die übrige Review-UI stabil ist (Phase 5).

---

## Guard-Determinismus vs. Skill-Pinning

Skills und Guards verfolgen bewusst **unterschiedliche Determinismus-Strategien**:

| | Skills | Guards |
| --- | --- | --- |
| **Binding-Zeitpunkt** | `link_skill` (Architekt verknüpft Skill mit Task) | Kontinuierlich (Scope-basiert) |
| **Versioniert?** | Ja — Task pinnt auf exakte Skill-Version | Nein — Guards sind nicht inhaltlich versioniert (`guards.version` ist ein **Optimistic-Locking-Counter** für Concurrency, kein Versions-Tracking) |
| **Neue Einträge nach Task-Start** | Keine — Pinning ist unveränderlich | Möglich — neue `active` Guards erscheinen mit `pending` |
| **Ziel** | Deterministische Instruktion | Kontinuierliche Qualitätssicherung |

**Rationale:** Skill-Pinning sichert, dass der Worker dieselben Anweisungen sieht die der Architekt erwartet hat. Guard-Dynamik hingegen ist gewollt: wenn ein neues Sicherheits-Guard aktiviert wird, soll es auf alle laufenden Tasks angewendet werden — nicht erst auf zukünftige.

**Konsequenz für laufende Tasks:** Ein Guard der nach `in_progress` hinzugefügt wird, erscheint in `get_guards` mit `status: pending`. Der Worker ist verantwortlich, ihn zu prüfen — er blockiert den `in_review`-Übergang wie jeder andere Guard.

---

### Error Handling — fehlende Guard-Einträge

`hivemind/get_guards` gibt für jeden aktiven Guard einen `task_guards`-Eintrag zurück. Falls ein Guard neu hinzugekommen ist (nach Task-Start), wird er dynamisch mit `status: pending` hinzugefügt.

Fehlerfall `report_guard_result`:

- `guard_id` existiert nicht → `404 Guard not found`
- Guard gehört nicht zum Task-Scope → `403 Guard not applicable`
- Guard bereits `passed` → idempotenter Noop (kein erneuter Write)
- Guard `skipped` ohne Begründung → Backend fordert `result`-Text

---

## Guards und Context Boundary

Guards sind **scope-based, nicht context-boundary-based**. Die Context Boundary (gesetzt vom Architekten via `set_context_boundary`) steuert welche Skills und Docs geladen werden — nicht welche Guards gelten.

Guards werden **immer vererbt** wenn ihr `scope` zum Task passt — unabhängig davon ob eine Context Boundary gesetzt ist. Ein eng gesetzter Context kann die Skills einschränken, aber nicht die Guards umgehen.

---

## Kartograph-Discovery

Der Kartograph entdeckt Guards automatisch beim Repo-Analyse:

### Quellen

| Datei | Mögliche Guards |
| --- | --- |
| `.github/workflows/ci.yml` | CI-Jobs → `executable` Guards |
| `Makefile` / `Taskfile.yml` | `make lint`, `make test` → `executable` Guards |
| `package.json` scripts | `npm run lint`, `npm run test` → `executable` Guards |
| `pyproject.toml [tool.ruff]` | Ruff-Config → Guard "ruff check ." |
| `pyproject.toml [tool.pytest]` | Pytest-Config → Guard "pytest" |
| `.pre-commit-config.yaml` | Pre-commit Hooks → `executable` Guards |
| README / CONTRIBUTING.md | Manuelle Regeln → `manual` Guards |

### Kartograph-Vorschlag-Flow

```text
Kartograph analysiert Repo
  → erkennt: pyproject.toml mit [tool.ruff] + [tool.pytest.ini_options]
  → erstellt Guard-Proposals:
     hivemind/propose_guard {
       "title": "Python Linting",
       "type": "executable",
       "command": "ruff check .",
       "scope": ["backend"],
       "project_id": "uuid"
     }
  → Proposer reicht Proposal ein (`submit_guard_proposal`) → lifecycle: draft → pending_merge
  → Admin mergt → lifecycle: pending_merge → active
  → Guard wird automatisch auf alle Tasks mit scope=backend angewendet
```

---

## Skill-Guard-Verbindung

Skills können eigene Guards tragen — wer den Skill nutzt, muss die Guards bestehen:

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

## Skill: FastAPI Endpoint erstellen
...
```

Das macht Skills zu **vollständigen, ausführbaren Arbeitsanweisungen** — nicht nur Instruktionen, sondern auch Verifikation eingebaut.

---

## Lifecycle

Guards folgen demselben Lifecycle wie Skills:

```text
[Draft] → [Pending Merge] → [Active] → [Deprecated]
                         ↘ [Rejected]
```

| State | Bedeutung | Nächster Schritt |
| --- | --- | --- |
| `draft` | Kartograph (primär), Developer oder Admin hat Guard vorgeschlagen | Proposer reicht via `submit_guard_proposal` zur Review ein |
| `pending_merge` | Admin-Review läuft | Admin mergt (`merge_guard`) **oder** rejected (`reject_guard`) |
| `active` | Guard gilt für alle Tasks im definierten Scope | Proposal für Änderung nötig |
| `rejected` | Admin hat Proposal abgelehnt — Proposer erhält Begründung | Neues Proposal möglich |
| `deprecated` | Guard nicht mehr gültig (z.B. Tool ersetzt) — lesbar für Audit | — |

Guard-Änderungen laufen über Proposals (wie Skill-Changes) — kein direkter Hard-Overwrite.

---

## MCP-Tools

```text
hivemind/get_guards         { "task_id": "TASK-88" }
  → liefert alle Guards (global + project + skill + task) mit Status

hivemind/report_guard_result { "task_id": "TASK-88",
                               "guard_id": "uuid",
                               "status": "passed|failed|skipped",
                               "result": "output text" }

hivemind/propose_guard      { "title": "...", "type": "executable",
                               "command": "...", "scope": [...],
                               "project_id": "uuid|null",
                               "skill_id": "uuid|null" }

hivemind/propose_guard_change { "guard_id": "uuid", "diff": "...", "rationale": "..." }

hivemind/submit_guard_proposal { "guard_id": "uuid" } -- draft → pending_merge
```

---

## Datenmodell

```sql
CREATE TABLE guards (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID REFERENCES projects(id),   -- NULL = global
  skill_id    UUID REFERENCES skills(id),      -- NULL = nicht skill-spezifisch
  title       TEXT NOT NULL,
  description TEXT,
  type        TEXT NOT NULL DEFAULT 'executable', -- executable|declarative|manual
  command     TEXT,           -- für executable: "pytest --cov-fail-under=80"
  condition   TEXT,           -- für declarative: maschinenlesbare Bedingung
  scope       TEXT[] DEFAULT '{}',  -- ["backend", "frontend"] — leer = alle
  lifecycle   TEXT NOT NULL DEFAULT 'draft', -- draft|pending_merge|active|rejected|deprecated
  created_by  UUID NOT NULL REFERENCES users(id),
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE task_guards (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id    UUID NOT NULL REFERENCES tasks(id),
  guard_id   UUID NOT NULL REFERENCES guards(id),
  status     TEXT NOT NULL DEFAULT 'pending', -- pending|passed|failed|skipped
  result     TEXT,                            -- Output des executable Guards
  checked_at TIMESTAMPTZ,
  checked_by UUID REFERENCES users(id),       -- NULL = automatisch
  UNIQUE(task_id, guard_id)
);
```

---

## Abgrenzung zu DoD

| | Definition of Done | Guard |
| --- | --- | --- |
| Art | Deklarativ | Executable / Declarative / Manual |
| Scope | Pro Task (vom Architekten) | Global / Project / Skill / Task |
| Prüfung | Owner beim Review (manuell) | Worker vor in_review (automatisierbar) |
| Fehlschlag | Owner rejected → `qa_failed` | Guard failed → Task bleibt `in_progress`; `in_review`-Übergang gibt 422 zurück |
| Discovery | Architekt definiert | Kartograph entdeckt aus Repo |
| Versioniert | Teil von task.definition_of_done JSONB | Eigenständige Entities mit Lifecycle |

DoD und Guards **ergänzen sich**: Guards prüfen automatisch; was nicht automatisch prüfbar ist, bleibt DoD-Kriterium für den Owner.
