# Epic Restructure Proposal

← [Index](../../masterplan.md)

**Verfügbar ab:** Phase 4 (Architekt-Writes, nachdem Kartograph Code-Nodes kartiert hat)
**Erstellt von:** Kartograph (via `propose_epic_restructure` MCP-Tool)
**Genehmigt von:** Admin (oder Owner mit `manage_epic`-Berechtigung)

---

## Wozu braucht es das?

Der Kartograph erkundet die Codebase bottom-up. Dabei deckt er oft Diskrepanzen zwischen der geplanten Epic-Struktur und der tatsächlichen Code-Organisation auf:

```text
Geplante Epic-Struktur:
  EPIC-5 "Auth-System"   → TASK-10, TASK-11, TASK-12
  EPIC-6 "Dashboard"     → TASK-20, TASK-21

Kartograph entdeckt:
  auth/ ist ein eigenständiges Paket mit 3 Sub-Modulen
  → Sinnvoller: auth_core + auth_oauth + auth_mfa als separate Epics
  → TASK-11 und TASK-12 gehören eigentlich zu auth_oauth, nicht auth_core
```

Ein Epic Restructure Proposal schlägt vor, Epics zu **splitten**, zu **mergen** oder **Tasks zu verschieben** (zwischen Epics), um die Epic-Struktur an die tatsächliche Code-Struktur anzupassen.

---

## State Machine

```text
┌──────────────────────────────────────────────────────┐
│                                                      │
│   [proposed] ──── Admin accept ───→ [accepted]       │
│       │                                 │            │
│       │                           apply_restructure  │
│       │                                 │            │
│       └──── Admin reject ───→ [rejected]▼            │
│                                    [applied]         │
└──────────────────────────────────────────────────────┘
```

| State | Bedeutung |
| --- | --- |
| `proposed` | Kartograph hat den Vorschlag erstellt; Admin-Review ausstehend |
| `accepted` | Admin hat den Vorschlag genehmigt; wartet auf Ausführung |
| `applied` | Restructure wurde ausgeführt; Epics + Tasks sind umstrukturiert |
| `rejected` | Admin hat den Vorschlag abgelehnt; bleibt als historischer Eintrag |

### Transitionen

| Von | Nach | Wer | Tool |
| --- | --- | --- | --- |
| `proposed` | `accepted` | Admin | `accept_epic_restructure` |
| `proposed` | `rejected` | Admin | `reject_epic_restructure` |
| `accepted` | `applied` | System (auf Admin-Trigger) | `apply_epic_restructure` |

> **Keine Auto-Apply:** `accepted` → `applied` erfordert einen expliziten `apply_epic_restructure`-Call. Das gibt dem Admin Zeit, die Auswirkungen zu prüfen, bevor Tasks und Epics tatsächlich umstrukturiert werden. Die Preview (`accepted`-State mit Diff) zeigt was sich ändern wird.

---

## Proposal-Typen

### 1. Epic Split

Ein Epic wird in zwei oder mehr Epics aufgeteilt. Bestehende Tasks werden auf die neuen Epics verteilt.

```json
{
  "type": "split",
  "source_epic_id": "EPIC-5",
  "resulting_epics": [
    {
      "title": "Auth Core",
      "description": "Basis-Authentifizierung: JWT, Session, RBAC",
      "task_ids": ["TASK-10"]
    },
    {
      "title": "Auth OAuth",
      "description": "OAuth2-Integration: Google, GitHub",
      "task_ids": ["TASK-11", "TASK-12"]
    }
  ],
  "rationale": "Kartograph hat auth/ in drei Sub-Module aufgeteilt. auth_core und auth_oauth sind konzeptuell getrennte Concerns.",
  "code_node_refs": ["code-node-uuid-auth-core", "code-node-uuid-auth-oauth"]
}
```

### 2. Epic Merge

Zwei oder mehr Epics werden zu einem zusammengeführt.

```json
{
  "type": "merge",
  "source_epic_ids": ["EPIC-8", "EPIC-9"],
  "resulting_epic": {
    "title": "CI/CD Pipeline",
    "description": "Vollständige CI/CD-Infrastruktur inkl. Deployment",
    "task_ids": ["TASK-30", "TASK-31", "TASK-32", "TASK-33"]
  },
  "rationale": "EPIC-8 (CI) und EPIC-9 (CD) teilen denselben Codebereich (.github/workflows/) und dieselben Guards. Getrennte Epics erhöhen administrative Overhead ohne Mehrwert."
}
```

### 3. Task Move

Tasks werden von einem bestehenden Epic in ein anderes verschoben (kein neues Epic nötig).

```json
{
  "type": "task_move",
  "moves": [
    {
      "task_id": "TASK-15",
      "from_epic_id": "EPIC-5",
      "to_epic_id": "EPIC-6",
      "rationale": "TASK-15 betrifft das Dashboard-Auth-Widget, nicht die Core-Auth-Logik"
    }
  ]
}
```

---

## Constraints

### Welche Tasks können verschoben / restrukturiert werden?

| Task-State | Kann verschoben werden? | Begründung |
| --- | --- | --- |
| `incoming`, `scoped`, `ready` | **Ja** | Noch nicht begonnen |
| `in_progress` | **Nein** | Aktiver Worker — Umstrukturierung würde Kontext invalidieren |
| `in_review` | **Nein** | Review läuft — Owner muss abschließen |
| `blocked` | **Ja, mit Admin-Bestätigung** | Offener Decision Request wird mitgenommen; `epic_id` und `owner_id` aktualisiert |
| `escalated` | **Nein** | Eskalation muss erst aufgelöst werden |
| `done`, `cancelled` | **Nein** | Terminal-States; bleiben im ursprünglichen Epic als historischer Record |

> **`in_progress`/`in_review`-Blocker:** Wenn ein Restructure-Proposal Tasks in `in_progress` oder `in_review` enthält, kann er zwar `accepted` werden (Preview sichtbar), aber `apply_epic_restructure` gibt HTTP 422 zurück bis alle blockierenden Tasks in einem verschiebbaren State sind. Die UI zeigt: "Warte auf 2 Tasks" mit Links zu TASK-11 und TASK-12.

---

## Apply-Flow — End-to-End

`apply_epic_restructure` führt die tatsächliche Restrukturierung in **einer einzigen Datenbank-Transaktion** durch. Je nach `restructure_type` unterscheidet sich der Ablauf:

### Apply: Epic Split

```text
1. Validierung:
   - Proposal.state == 'accepted'
   - Source-Epic existiert und ist in incoming|scoped|in_progress
   - Alle referenzierten Tasks sind in verschiebbarem State (incoming|scoped|ready|blocked)
   - Kein Task in in_progress|in_review|escalated|done|cancelled → HTTP 422

2. Ausführung (atomar):
   a) Für jedes resulting_epic in payload.resulting_epics:
      → INSERT neues Epic (state übernommen vom Source-Epic; owner = Source-Epic owner)
      → epic_key via Sequence generieren (EPIC-{n}, fortlaufend)
   b) Für jeden Task in resulting_epics[].task_ids:
      → UPDATE tasks SET epic_id = <neues_epic_id>
      → task_node_links, decision_requests.epic_id migrieren
   c) Source-Epic:
      → Wenn ALLE Tasks verschoben → Source-Epic state → 'cancelled', Begründung: "Split via RESTRUCTURE-X"
      → Wenn Restliche Tasks bleiben → Source-Epic bleibt unverändert
   d) epic_restructure_proposals.state → 'applied', applied_at = NOW()

3. Side-Effects:
   → Notification 'restructure_applied' an Epic-Owner + alle betroffenen Task-Assignees
   → Audit-Eintrag in mcp_invocations
   → Falls Federation: sync_outbox-Einträge für neue Epics (wenn Tasks auf Peers delegiert)
```

### Apply: Epic Merge

```text
1. Validierung:
   - Proposal.state == 'accepted'
   - Alle Source-Epics existieren und sind nicht cancelled|done
   - Alle Tasks in allen Source-Epics sind in verschiebbarem State
   - Kein Task in in_progress|in_review|escalated → HTTP 422

2. Ausführung (atomar):
   a) INSERT neues Merge-Epic:
      → Title + Description aus payload.resulting_epic
      → State: 'in_progress' wenn ein Source-Epic in_progress war, sonst 'scoped'
      → Owner: Owner des ersten Source-Epics (oder explizit in Payload)
   b) Für jeden Task in allen Source-Epics:
      → UPDATE tasks SET epic_id = <merge_epic_id>
      → task_node_links, decision_requests.epic_id migrieren
   c) Alle Source-Epics → state: 'cancelled', Begründung: "Merged into [EPIC-X] via RESTRUCTURE-X"
   d) epic_node_links: Vereinigung aller Source-Epic-Links auf das neue Epic
   e) epic_restructure_proposals.state → 'applied', applied_at = NOW()

3. Side-Effects: (identisch mit Split)
```

### Apply: Task Move

```text
1. Validierung:
   - Proposal.state == 'accepted'
   - Für jeden Move in payload.moves:
     → Source-Epic und Target-Epic existieren und sind nicht cancelled|done
     → Task ist in verschiebbarem State (incoming|scoped|ready|blocked)
     → Task gehört aktuell zu from_epic_id

2. Ausführung (atomar):
   a) Für jeden Move:
      → UPDATE tasks SET epic_id = <to_epic_id> WHERE id = <task_id>
      → Falls Task blocked: zugehöriger decision_request.epic_id migrieren
   b) epic_restructure_proposals.state → 'applied', applied_at = NOW()

3. Side-Effects:
   → Notification an Task-Assignees: "TASK-X verschoben von EPIC-A nach EPIC-B"
   → Falls Federation + Task.assigned_node_id: sync_outbox-Eintrag für Peer
```

### Fehlerbehandlung

| Fehler | HTTP | Verhalten |
| --- | --- | --- |
| Proposal nicht `accepted` | 409 | "Proposal must be in state 'accepted'" |
| Blockierende Tasks vorhanden | 422 | `{ "blocking_tasks": ["TASK-11", "TASK-12"], "states": ["in_progress", "in_review"] }` |
| Source-Epic nicht gefunden | 404 | Standard |
| Source-Epic done/cancelled | 422 | "Cannot restructure terminal-state epic" |
| DB-Constraint-Verletzung | 500 | Rollback der gesamten Transaktion; Proposal bleibt `accepted` |

### Epic-State-Constraints bei Merge/Split

- **Split:** Source-Epic muss in `incoming`, `scoped` oder `in_progress` sein. Kein Split von `done`-Epics.
- **Merge:** Alle Source-Epics müssen im selben State sein oder im State `scoped`. Wenn ein Source-Epic `in_progress` ist, wird das Merge-Epic direkt auf `in_progress` gesetzt.
- **Task Move:** Source- und Target-Epic müssen existieren und dürfen nicht `cancelled` oder `done` sein.

---

## Datenmodell

```sql
CREATE TABLE epic_restructure_proposals (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proposal_key        TEXT NOT NULL UNIQUE,            -- "RESTRUCTURE-1", "RESTRUCTURE-2"
    state               TEXT NOT NULL DEFAULT 'proposed',
                        -- proposed | accepted | applied | rejected
    restructure_type    TEXT NOT NULL,                   -- split | merge | task_move
    payload             JSONB NOT NULL,                  -- Proposal-Spec (s.o.)
    rationale           TEXT NOT NULL,
    code_node_refs      UUID[] DEFAULT '{}',             -- referenzierte Code-Nodes
    proposed_by         UUID REFERENCES users(id),       -- Kartograph-User
    proposed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by         UUID REFERENCES users(id),       -- Admin/Owner
    reviewed_at         TIMESTAMPTZ,
    review_note         TEXT,                            -- Begründung bei Ablehnung
    applied_at          TIMESTAMPTZ,
    origin_node_id      UUID REFERENCES nodes(id),       -- Federation: Welcher Node hat den Vorschlag erstellt
    CONSTRAINT valid_state CHECK (state IN ('proposed', 'accepted', 'applied', 'rejected')),
    CONSTRAINT valid_type  CHECK (restructure_type IN ('split', 'merge', 'task_move'))
);

CREATE INDEX ON epic_restructure_proposals (state) WHERE state NOT IN ('applied', 'rejected');
```

---

## API-Endpoints

| Endpoint | Methode | Wer | Beschreibung |
| --- | --- | --- | --- |
| `/api/epic-restructure` | GET | Admin | Alle Proposals (filter: `state`) |
| `/api/epic-restructure` | POST | Kartograph | Neuen Proposal erstellen |
| `/api/epic-restructure/:key` | GET | Admin | Einzelner Proposal + Diff-Preview |
| `/api/epic-restructure/:key/accept` | POST | Admin | Proposal akzeptieren (→ `accepted`) |
| `/api/epic-restructure/:key/reject` | POST | Admin | Proposal ablehnen (→ `rejected`) |
| `/api/epic-restructure/:key/apply` | POST | Admin | Restructure ausführen (→ `applied`) |

### MCP-Tool

```json
{
  "name": "hivemind-propose_epic_restructure",
  "description": "Schlägt eine Restrukturierung der Epic-Hierarchie vor. Nur erlaubt wenn der Kartograph strukturelle Diskrepanzen zwischen Code-Organisation und Epic-Struktur erkannt hat.",
  "input_schema": {
    "restructure_type": "split | merge | task_move",
    "payload": "object (typ-spezifisch, s.o.)",
    "rationale": "string — Warum ist diese Restrukturierung sinnvoll?",
    "code_node_refs": ["uuid", "..."]
  }
}
```

**RBAC:** Nur Users mit `propose_epic_restructure`-Berechtigung (→ Kartograph-Rolle + Admin).
**Accept/Reject/Apply:** Nur Admin (oder Owner mit `manage_epic`-Berechtigung).

---

## Diff-Preview (GET `/api/epic-restructure/:key`)

Im `accepted`-State zeigt die API eine vollständige Preview der geplanten Änderungen:

```json
{
  "proposal_key": "RESTRUCTURE-3",
  "state": "accepted",
  "preview": {
    "epics_created": [
      { "title": "Auth Core", "tasks": ["TASK-10"] },
      { "title": "Auth OAuth", "tasks": ["TASK-11", "TASK-12"] }
    ],
    "epics_archived": ["EPIC-5"],
    "tasks_moved": [
      { "task_key": "TASK-10", "from": "EPIC-5", "to": "new:auth-core" },
      { "task_key": "TASK-11", "from": "EPIC-5", "to": "new:auth-oauth" },
      { "task_key": "TASK-12", "from": "EPIC-5", "to": "new:auth-oauth" }
    ],
    "blocking_tasks": []
  }
}
```

Wenn `blocking_tasks` nicht leer ist, kann `apply` nicht ausgeführt werden — die UI zeigt die blockierenden Tasks mit Links.

---

## Triage Integration

Neue Proposals erscheinen in der **Triage Station** unter `[RESTRUCTURE PROPOSAL]`:

```text
┌─ TRIAGE ────────────────────────────────────────────┐
│  [RESTRUCTURE PROPOSAL]  RESTRUCTURE-3              │
│  Epic Split: EPIC-5 → Auth Core + Auth OAuth        │
│  Kartograph · auth/, 3 Code-Nodes referenziert      │
│  [DETAILS]  [AKZEPTIEREN]  [ABLEHNEN]               │
└─────────────────────────────────────────────────────┘
```

---

## Federation

Epic Restructure Proposals sind **lokal** (kein `federation_scope`). Der Grund: Ein Restructure verändert die Epic/Task-Struktur auf dem Origin-Node. Peers empfangen die resultierenden State-Änderungen (neue Epics, verschobene Tasks) via normalen Federation-Sync — nicht das Proposal selbst.

**Ablauf mit Federation:**
1. Kartograph auf Node A erstellt `RESTRUCTURE-3`
2. Admin auf Node A akzeptiert + wendet an
3. Neue Epics (`Auth Core`, `Auth OAuth`) werden auf Node A erstellt
4. Falls Tasks auf einem Peer-Node (`assigned_node_id`) lagen → Federation-Update (Task hat neue `epic_id`)
5. Peer-Node empfängt `epic_share`-Update mit neuer Epic-Zuordnung
