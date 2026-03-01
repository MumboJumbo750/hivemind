# State Machines & Concurrency

← [Index](../../masterplan.md)

---

## Task State Machine

```text
                    ┌──────────┐
                    │ incoming │ ← externes Event, manuell angelegt
                    └────┬─────┘
                         │ Owner scopt Epic
                    ┌────▼─────┐
                    │  scoped  │
                    └────┬─────┘
                         │ Architekt zerlegt in Tasks
                    ┌────▼─────┐
                    │  ready   │ ← Context Boundary gesetzt, DoD definiert
                    └────┬─────┘
                         │ Worker startet
               ┌─────────▼──────────┐
               │    in_progress     │◄──────────────────┐
               └─────────┬──────────┘                   │
                         │ Worker submittet             qa_failed
               ┌─────────▼──────────┐                   │
               │     in_review      │───────────────────►┘
               └─────────┬──────────┘
                         │ Owner approved
                    ┌────▼─────┐
                    │   done   │
                    └──────────┘

Sonderstates:
  blocked    — aus in_progress, Worker blockiert, wartet auf Entscheidung
  escalated  — aus qa_failed (Worker versucht in_progress bei qa_failed_count >= 3) ODER aus blocked (Decision-Request-SLA > 72h ohne Auflösung)
  cancelled  — aus incoming|scoped|ready|in_progress|blocked|escalated durch Admin (nicht aus done/in_review)
```

### Erlaubte Transitionen

| Von | Nach | Wer |
| --- | --- | --- |
| `incoming` | `scoped` | Owner (manuelle Aktion) |
| `scoped` | `ready` | Architekt (nach Dekomposition) |
| `ready` | `in_progress` | Worker |
| `in_progress` | `in_review` | Worker (nach submit_result) |
| `in_review` | `done` | Owner/Admin (`approve_review`) |
| `in_review` | `qa_failed` | Owner/Admin (`reject_review`) |
| `qa_failed` | `in_progress` | Worker (nur wenn `qa_failed_count < 3`; expliziter Re-entry via `update_task_state { "state": "in_progress" }`) |
| `qa_failed` | `escalated` | System (wenn Worker `in_progress` anfordert aber `qa_failed_count >= 3` → System setzt `escalated` statt `in_progress`) |
| `in_progress` | `blocked` | Worker (`create_decision_request`, atomar) |
| `blocked` | `in_progress` | Owner/Admin (via `resolve_decision_request` — setzt Task automatisch auf `in_progress`) |
| `blocked` | `escalated` | System (Decision-Request-SLA > 72h ohne Admin-Resolve) |
| `escalated` | `in_progress` | Admin (`resolve_escalation`) |
| `incoming`, `scoped`, `ready`, `in_progress`, `blocked`, `escalated` | `cancelled` | Admin only |

### Regeln

- `done` **nur** aus `in_review` — kein Überspringen
- **Phase 1–4:** `in_review` nur wenn `result` vorhanden (Backend-Prüfung via `update_task_state`). Guard-Status wird **nicht** geprüft — der `in_review`-Übergang ist auch ohne bestandene Guards möglich. Guards sind in diesen Phasen als Checkliste für den Worker gedacht, aber kein technischer Blocker.
- **Ab Phase 5:** `in_review` **nur** wenn `result` vorhanden **und** alle Guards `passed|skipped`. Das Backend gibt 422 zurück wenn noch Guards `pending` oder `failed` sind.
- **DoD-Prüfung ist keine automatische Eintrittsbedingung für `in_review`** — DoD wird vom Owner im Review Panel manuell abgehakt. Fehlende DoD-Kriterien führen zu Owner-Reject (`qa_failed`), nicht zu einem 422-Fehler beim State-Übergang.
- Bei Owner-Reject: `qa_failed` und Rückgabe an `in_progress` (Worker liest `review_comment`)
- **Review-Gate gilt immer** — auch im Solo-Modus (Self-Review erlaubt, aber Schritt nicht überspringbar). **Solo-Mode technische Enforcement:** Das Backend prüft NICHT `assigned_to != reviewer_id` — im Solo-Modus ist der einzige User immer beides gleichzeitig (Worker und Owner). Das Review-Gate ist ein **prozeduraler Zwang** (kein technischer Lock): Der User muss aktiv `approve_review` oder `reject_review` aufrufen; es gibt keinen automatischen Durchlauf. Dies verhindert das unbeabsichtigte Überspringen des Review-Schritts, erzwingt aber keine Vier-Augen-Prüfung im Solo-Betrieb.
- **`qa_failed` ist ein persistenter State** — der Task bleibt auf `qa_failed` bis der Worker ihn aktiv wieder auf `in_progress` setzt. Das ermöglicht dem Worker den Review-Kommentar zu lesen bevor er weitermacht. Bei `qa_failed_count >= 3`: Worker-Versuch `in_progress` zu setzen wird vom System abgefangen → Task geht stattdessen auf `escalated`
- **Guard-Reset bei `qa_failed → in_progress`:** Alle `task_guards`-Einträge für den Task werden auf `status = 'pending'` zurückgesetzt — unabhängig vom vorherigen Status (`pending`, `failed` oder `skipped`). Das bedeutet: auch ein bereits `failed`er Guard wird auf `pending` zurückgesetzt. Der Worker darf ohne Code-Änderung erneut versuchen einen Guard zu bestehen. Der Worker muss alle Guards erneut bestehen bevor er erneut `in_review` beantragen kann. Guards die manuell `skipped` wurden (Owner-Bestätigung), werden ebenfalls resettet — ein neuer Skip erfordert erneute Owner-Bestätigung.
- **`create_decision_request` ist atomar:** Das Tool erstellt den offenen Decision Request und setzt den Task in derselben DB-Transaktion von `in_progress` auf `blocked`
- **`decompose_epic` Initialstate:** Tasks die via `decompose_epic` oder `create_task` erstellt werden, starten im State `incoming`. Der Planer scopt sie (`incoming` → `scoped`), setzt Context Boundary + DoD, weist zu (`assign_task`), danach Transition auf `ready`
- **`cancelled` aus `in_review` ist nicht erlaubt** — Owner muss den Review abschließen (approve oder reject). Bei Epic-Cancel werden `in_review`-Tasks **nicht** automatisch gecancelt; der Owner muss sie zuerst reviewen
- **Stuck `in_review` bei Epic-Cancel:** Wenn ein Epic gecancelt wird und Tasks in `in_review` verbleiben, die der Owner > 72h nicht abschließt: Backup-Owner (wenn gesetzt) oder Admins erhalten nach 72h Owner-Inaktivität die Review-Berechtigung (→ [rbac.md — Governance-Delegation](./rbac.md#governance-delegation--entlastungsmechanik)). Als absoluter Notfall-Exit kann ein Admin `cancel_task --force` ausführen — dieser Aufruf ist nur erlaubt wenn `task.state = 'in_review'` UND `epic.state = 'cancelled'` UND `owner_inactive_hours >= 72`. Der Force-Cancel wird im Audit-Log mit `force_cancel=true` markiert.
- **Auto-Delegation bei Owner-Inaktivität:** Wenn der Owner > 72h inaktiv ist und `in_review`-Tasks blockieren, übernimmt der Backup-Owner (wenn gesetzt) oder Projekt-Admins die Review-Berechtigung (→ [rbac.md — Governance-Delegation](./rbac.md#governance-delegation--entlastungsmechanik))

---

## Epic State Machine

```text
               ┌──────────┐
               │ incoming │ ← manuell angelegt oder via Webhook
               └────┬─────┘
                    │ Owner scopt (Priorität, SLA, DoD-Rahmen)
               ┌────▼─────┐
               │  scoped  │
               └────┬─────┘
                    │ Architekt zerlegt in Tasks (mindestens 1 Task auf ready)
            ┌───────▼────────┐
            │  in_progress   │ ← sobald mindestens ein Task in_progress
            └───────┬────────┘
                    │ alle Tasks done/cancelled
               ┌────▼─────┐
               │   done   │
               └──────────┘

Sonderstates:
  cancelled  — aus incoming|scoped|in_progress durch Admin
               cascadiert zu allen non-terminal Tasks AUSSER in_review
```

### Epic-Transitionen

| Von | Nach | Wer | Bedingung |
| --- | --- | --- | --- |
| `incoming` | `scoped` | Owner | Owner, SLA, Priorität gesetzt |
| `scoped` | `in_progress` | System (automatisch) | Mindestens ein Task geht auf `in_progress` — ausgelöst im `update_task_state`-Handler (s.u.) |
| `in_progress` | `done` | System (automatisch) | Alle Tasks `done` oder `cancelled` — ausgelöst im `approve_review`- und `cancel_task`-Handler (s.u.) |
| `incoming`, `scoped`, `in_progress` | `cancelled` | Admin | Cascadiert Cancel auf non-terminal Tasks (außer `in_review`) |

### Epic Auto-Transition — Backend-Implementierung

Epic-Zustandsübergänge werden **nicht** durch einen separaten API-Call ausgelöst, sondern als Seiteneffekt in den Task-Mutations implementiert:

```python
# In update_task_state (nach erfolgreicher Task-Transition):
if new_task_state == "in_progress" and epic.state == "scoped":
    epic.state = "in_progress"   # atomar in derselben DB-Transaktion

# In approve_review (nach Task-Transition in_review → done):
if epic.state != "cancelled" and all(t.state in {"done", "cancelled"} for t in epic.tasks):
    epic.state = "done"          # atomar in derselben DB-Transaktion

# In cancel_task (nach Task-Transition → cancelled):
if epic.state != "cancelled" and all(t.state in {"done", "cancelled"} for t in epic.tasks):
    epic.state = "done"          # atomar in derselben DB-Transaktion
```

> Beide Epic-Auto-Transitionen laufen **atomar in derselben DB-Transaktion** wie die auslösende Task-Mutation. Kein separater Trigger, kein Polling — der Zustand ist immer konsistent.

### Epic-Cancel Cascade

Wenn ein Admin ein Epic cancelt:

1. Alle Tasks in `incoming`, `scoped`, `ready`, `in_progress`, `blocked`, `escalated` → `cancelled`
2. Tasks in `in_review` bleiben **unverändert** — Owner muss Review abschließen
3. Tasks in `done` oder `cancelled` bleiben unverändert
4. Offene `decision_requests` (`state = 'open'`) für gecancelte Tasks → `state = 'expired'`; SLA-Timer wird gestoppt
5. Erst wenn alle `in_review`-Tasks resolved sind, ist das Epic vollständig abgeschlossen

---

## Decision Request State Machine

```text
           ┌──────────┐
           │   open   │ ← Worker: create_decision_request (atomar mit Task → blocked)
           └────┬─────┘
                │
        ┌───────┼──────────────┐
        │       │              │
   ┌────▼──┐ ┌──▼──────┐ ┌───▼─────┐
   │resolved│ │ expired │ │escalated│
   └───────┘ └─────────┘ └─────────┘
```

### Decision Request Transitionen

| Von | Nach | Wer | Bedingung |
| --- | --- | --- | --- |
| `open` | `resolved` | Owner/Backup-Owner/Admin (`resolve_decision_request`) | Innerhalb SLA (72h) |
| `open` | `expired` | System (SLA-Cron) | 72h ohne Auflösung → Task `blocked → escalated`, DR `open → expired` |
| `open` | `escalated` | — | Kein eigenständiger Übergang — `expired` markiert den DR; der zugehörige Task geht auf `escalated` |

### Decision Request Regeln

- **Erstellt nur aus `in_progress`:** `create_decision_request` setzt den Task atomar auf `blocked`. Aufrufe aus anderen States → 409 Conflict.
- **Höchstens 1 offener DR pro Task:** Bevor ein neuer DR erstellt wird, prüft das Backend ob bereits `state = 'open'` für denselben Task existiert → 422 bei Duplikat. Zusätzlich DB-seitig abgesichert via `UNIQUE INDEX ON decision_requests(task_id) WHERE state = 'open'` (partielle Unique-Constraint).
- **`resolved` ist final:** Ein aufgelöster DR kann nicht erneut geöffnet werden. Bei erneutem Blocker: neuer DR erstellen.
- **`expired` ist final:** Ein abgelaufener DR kann nicht nachträglich resolved werden. Der Admin muss bei Eskalations-Auflösung (`resolve_escalation`) ggf. einen neuen DR erstellen oder die Entscheidung direkt dokumentieren.
- **SLA-Kette:** 24h → Owner-Notification, 48h → Backup-Owner-Notification (wenn vorhanden), 72h → `expired` + Task `escalated` + Admin-Notification.
- **SLA-Kette im Solo-Modus / NULL-Owner:** Wenn `epics.owner_id = NULL` (unmöglich — Owner ist bei Epic-Erstellung Pflichtfeld) oder `backup_owner_id = NULL` (erlaubt): Der 24h-Schritt wird ausgelöst an wen auch immer Owner ist. Bei `backup_owner_id = NULL` entfällt der 48h-Schritt — die SLA springt direkt nach 72h auf Admin-Notification + `escalated`. Im Solo-Modus mit einem einzigen User: dieser User ist Owner und Admin gleichzeitig — er erhält alle drei Notifications (24h, direkt → 72h) und muss selbst auflösen.
- **Idempotenz:** `resolve_decision_request` mit identischer `idempotency_key` auf bereits resolved DR → Noop (kein Fehler).
- **Cascading bei Epic-Cancel:** Offene DRs (`state = 'open'`) für gecancelte Tasks → `state = 'expired'`; SLA-Timer gestoppt.

---

## Concurrency: Optimistic Locking

Jeder mutierende Write auf eine bestehende Entität muss `expected_version` und `idempotency_key` mitschicken:

```json
{
  "request_id": "uuid",
  "actor_id": "uuid",
  "actor_role": "developer|admin|service|kartograph",
  "epic_id": "uuid",
  "idempotency_key": "uuid",
  "expected_version": 12
}
```

> Epics werden API-seitig per `epic_key` referenziert (z.B. `"EPIC-12"`), intern aber auf `epics.id` (UUID) aufgelöst. Tasks werden API-seitig per `task_key` referenziert (z.B. `"TASK-88"`), intern aber auf `tasks.id` (UUID) aufgelöst. Siehe [mcp-toolset.md — Identifier-Konvention](./mcp-toolset.md#identifier-konvention).

- **`expected_version` mismatch** → HTTP 409 Conflict — Client muss reload und retry
- **`idempotency_key` bereits bekannt** → selbe Response wie beim ersten Aufruf (kein Fehler)
- Antwort enthält immer `audit_id`; bei versionierten Entitäten zusätzlich `new_version`

---

## Skill Lifecycle

```text
[Draft] → [Pending Merge] → [Active] → [Deprecated]
                         ↘ [Rejected]
```

| State | Bedeutung | Wer kann weiter |
| --- | --- | --- |
| `draft` | Gaertner hat Proposal erstellt | Proposer reicht via `submit_skill_proposal` zur Review ein |
| `pending_merge` | Admin-Review läuft | Admin `merge_skill` oder `reject_skill` |
| `active` | Bibliotekar schlägt vor, Tasks pinnen darauf | Gaertner erstellt Change-Proposal |
| `rejected` | Admin hat Proposal abgelehnt — Gaertner erhält Begründung | Neues Proposal möglich |
| `deprecated` | Nicht mehr vorgeschlagen, bleibt lesbar für Audit | — |

### Skill/Guard Change-Proposal-Flow

Für bestehende aktive Skills/Guards läuft eine Änderung über einen separaten Proposal-Flow:

```text
Gaertner/Kartograph: propose_skill_change  → Eintrag in skill_change_proposals (state: open)
Gaertner/Kartograph: propose_guard_change  → Eintrag in guard_change_proposals  (state: open)

Admin: accept_skill_change → state: open → accepted; diff wird angewendet → neuer skill_versions-Eintrag
Admin: reject_skill_change → state: open → rejected; review_note an Proposer
Admin: accept_guard_change → state: open → accepted; guard wird aktualisiert
Admin: reject_guard_change → state: open → rejected; review_note an Proposer
```

> Der Skill-/Guard-Lifecycle (`draft → pending_merge → active`) gilt für **neue** Skills/Guards.
> Change-Proposals (`skill_change_proposals`, `guard_change_proposals`) sind der separate Flow für **Änderungen** an bereits aktiven Entitäten.
> Triage Station zeigt beide Queues: `[SKILL PROPOSAL]` (neue Skills) und `[SKILL CHANGE]` / `[GUARD CHANGE]` (Änderungen).

### Skill-Versionierung & Task-Pinning

- Tasks pinnen auf die Skill-Version die zum Zeitpunkt von `link_skill` `active` war (nicht Task-Erstellung)
- Skill-Updates während `in_progress` beeinflussen den laufenden Task **nicht**
- Neue Skill-Verknüpfungen erhalten immer die aktuelle `active`-Version
- `skill_versions` ist **immutable** (append-only, kein Delete, kein Update)
- Deprecated Skills bleiben lesbar für Audit, werden dem Bibliotekar nicht mehr zur Auswahl angeboten

---

## Context Boundary

Eine Context Boundary ist eine **deklarative Scope-Definition** pro Task, gesetzt vom Architekten:

```json
{
  "task_id": "TASK-88",
  "allowed_skills": ["uuid-skill-1", "uuid-skill-2"],
  "allowed_docs": ["uuid-doc-1"],
  "external_access": ["sentry"],
  "max_token_budget": 6000
}
```

- **Ohne gesetzte Boundary:** Bibliothekar verwendet pgvector-Similarity ohne Filterung
- **Mit gesetzter Boundary:** Nur explizit erlaubte Skills/Docs werden geladen
- **`external_access`:** Reserviert für Phase 8 — definiert welche externen Services der Worker im Task-Kontext abfragen darf (z.B. Sentry-API für Bug-Details). In Phase 1–7 nicht enforced, dient als Dokumentation der erlaubten Datenquellen im Worker-Prompt
- **Kartograph:** `context_boundary_filter: false` — Bibliotekar-Filterung deaktiviert
- **Wiki:** ignoriert Context Boundary immer — globales Hintergrundwissen ohne Projekt-Scope

> **Context Boundary ist kein Sicherheitsmechanismus** — sie ist ein **Fokus-Tool**. Ziel ist Token-Budget-Optimierung und Instruktionsqualität, nicht Zugriffskontrolle. Wiki und Kartograph sind bewusst boundary-exempt: Wiki-Wissen ist globales Hintergrundwissen; Kartograph braucht projekt-übergreifenden Kontext für Fog-of-War-Analyse. Zugriffskontrolle erfolgt via RBAC (`read_any_epic`, `read_any_doc`, etc.), nicht via Context Boundary.
> **Context Boundary & Guards:** Guards sind scope-based und gelten **unabhängig** von der Context Boundary. Eine eng gesetzte Boundary schränkt die geladenen Skills/Docs ein, aber nicht die angewendeten Guards. → Vollständige Erläuterung: [guards.md — Guards und Context Boundary](../features/guards.md#guards-und-context-boundary)

---

## Decision Request vs. Decision Record

| | Decision Request | Decision Record |
| --- | --- | --- |
| Erstellt von | Worker (wenn blockiert) | Gaertner (nach Abschluss) |
| Zeitpunkt | Während Task-Bearbeitung | Nach Task-Abschluss |
| Zweck | Entscheidungsbedarf eskalieren | Getroffene Entscheidung dokumentieren |
| SLA | 24h Owner, 48h Backup-Owner, 72h Admin | Nein |
| Verknüpfung | Task + Epic | Epic + optional Decision Request |

> **Auto-Transition:** `resolve_decision_request` setzt den zugehörigen Task automatisch von `blocked → in_progress`. Ein separater `update_task_state`-Call ist nicht nötig.
> **Owner-Sync:** `reassign_epic_owner` aktualisiert auch `owner_id` und `backup_owner_id` auf allen offenen `decision_requests` (`state = 'open'`) des Epics, damit SLA-Notifications korrekt geroutet werden.

---

## Eskalations-Flow

```text
Task in_progress
  │
  ├─ 3x qa_failed (via reject_review) ─────────────→ escalated
  │                                                       │
  ├─ Worker: create_decision_request                      │
  │   └─ setzt atomar in_progress → blocked               │
  │       SLA: 24h → Owner Notification                   │
  │       SLA: 48h → Backup-Owner Notification            │
  │       SLA: 72h → System-Automatik ───────────────→ escalated (blocked → escalated)
  │                                                       │
  │   Normale Auflösung (vor 72h):                        │
  └─ Owner/Admin: resolve_decision_request ────────→ in_progress
  │
  │   Eskalations-Auflösung (nach 72h oder 3x qa_failed):
  └─ Admin: resolve_escalation ──────────────────────────→ in_progress (setzt qa_failed_count = 0)
```

SLA-Kette (Decision Request):

1. 24h → Owner wird notifiziert (In-App)
2. 48h → Backup-Owner wird notifiziert (bei `backup_owner_id = NULL`: direkt zu Schritt 3)
3. 72h → Admin-Fallback: Task wechselt automatisch von `blocked` → `escalated`; Decision Request `state` → `expired`
4. Admin löst `escalated` auf → `in_progress`
5. Jede Eskalation endet **deterministisch** mit einer Resolution

> **`expired` Decision Requests:** Wenn ein Decision Request via 72h-SLA auf `expired` gesetzt wird, bleibt er als historischer Eintrag lesbar. Der Admin kann bei der Eskalations-Auflösung entweder einen neuen Decision Request erstellen oder die Entscheidung direkt treffen. Ein `expired` Decision Request kann nicht nachträglich `resolved` werden — nur neue Requests sind möglich.
