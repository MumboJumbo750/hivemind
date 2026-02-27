# MCP Tool-Set

← [Index](../../masterplan.md)

Hivemind ist selbst ein MCP-Server. Alle Tools folgen demselben Sicherheitsmodell: AuthN + AuthZ + Idempotenz + Audit.

**Tool-Naming-Konvention:** Alle Tools verwenden den Namespace-Prefix `hivemind/` gefolgt vom Tool-Namen in `snake_case`. Beispiel: `hivemind/get_task`, `hivemind/create_epic`. Kein Tool verwendet `hm/` oder einen anderen Prefix. Intern (Code, Logs, Audit) wird der volle Name `hivemind/<tool>` verwendet.

---

## Transports

| Transport | Einsatz | Konfiguration |
| --- | --- | --- |
| **stdio** | Lokale Clients (Claude Desktop, Cursor, etc.) | Standard |
| **HTTP/SSE** | Web-Clients, Remote-Instanzen, Team-Setup | `HIVEMIND_TRANSPORT=http` |

Beide Transports über denselben FastAPI-Service.

---

## Read Tools

### Rollen `developer` | `admin` | `kartograph`

```text
hivemind/get_epic           { "id": "uuid" }
hivemind/get_task           { "id": "TASK-88" }         -- task_key, nicht UUID
hivemind/get_skills         { "task_id": "TASK-88" }    -- Bibliothekar-gefiltert
hivemind/get_skill_versions { "skill_id": "uuid" }      -- immutable Versionshistorie
hivemind/get_guards         { "task_id": "TASK-88" }    -- alle Guards (global+project+skill+task)
hivemind/get_doc            { "id": "uuid" }
hivemind/get_wiki_article   { "id": "uuid" | "slug": "auth-architektur" }
hivemind/search_wiki        { "query": "authentication", "tags": ["backend"] }
hivemind/list_projects      { "limit": 50, "offset": 0 }
hivemind/list_epics         { "project_id": "uuid",     -- Pflicht
                              "state": "...",            -- optional Filter
                              "limit": 50, "offset": 0 }
hivemind/list_tasks         { "epic_id": "uuid",         -- optional
                              "state": "...",            -- optional Filter
                              "assigned_to": "uuid",     -- optional Filter
                              "limit": 50, "offset": 0 }
hivemind/list_peers         { "state": "online|offline|all" }
                              -- Gibt verbundene Peer-Nodes mit Name, Node-ID, Status, letztem Kontakt
                              -- und deren verfügbaren federated Skills zurück
                              -- Erfordert: developer-Rolle (Phase F)
hivemind/get_prompt         { "type": "...",            -- Pflicht, siehe unten
                              "task_id": "TASK-88",     -- Pflicht für: bibliothekar, worker, review
                                                        -- optional für: gaertner (mind. eines von task_id/epic_id Pflicht)
                              "epic_id":  "uuid" }      -- Pflicht für: architekt
                                                        -- mind. eines von task_id/epic_id Pflicht für: gaertner
                                                        -- optional für: triage, kartograph
```

### Rolle `service` (minimale Scopes)

```text
hivemind/get_epic           { "id": "uuid" }
hivemind/get_task           { "id": "TASK-88" }
```

### Nur Admin (`triage` + `read_audit_log` Permission)

```text
hivemind/get_triage         { "state": "unrouted|escalated|dead|all" }
                              -- Erfordert: triage-Permission (admin only)
                              -- Enthält alle Event-Typen inkl. Federation (Phase F):
                              --   discovery_session (type='start|end'), peer_online, peer_offline,
                              --   federation_error — werden in Triage Station angezeigt

hivemind/get_audit_log      { "epic_id":   "uuid",      -- optional
                              "actor_id":  "uuid",      -- optional
                              "tool_name": "string",    -- optional
                              "from":      "ISO8601",   -- optional
                              "to":        "ISO8601",   -- optional
                              "limit":     50,          -- default 50, max 500
                              "offset":    0 }          -- Paginierung
                              -- Erfordert: read_audit_log-Permission (admin only)
```

> `get_triage` gibt Zugriff auf alle ungerouteten/eskalations-Items inkl. externer Payloads (Sentry Stack Traces).
> `get_audit_log` gibt Zugriff auf alle MCP-Invocations inkl. Eingabe-/Ausgabe-Payloads (bis Retention-Ablauf).
> Beide Tools sind daher auf Admin beschränkt.

---

## Identifier-Konvention

| Entität | Identifier | Beispiel | Verwendung in MCP-Tools |
| --- | --- | --- | --- |
| Task | `task_key` (TEXT) | `"TASK-88"` | `task_id`-Parameter in allen Tools |
| Epic | `epic_key` (TEXT) | `"EPIC-12"` | `epic_id`-Parameter in allen Tools |
| Skill | UUID | `"550e8400-e29b..."` | `skill_id`-Parameter |
| Guard | UUID | `"550e8400-e29b..."` | `guard_id`-Parameter |
| User | UUID | `"550e8400-e29b..."` | `actor_id`-Parameter |

> API-seitig werden Epics per `epic_key` referenziert (`"EPIC-12"`). Das Backend löst den Key intern auf `epics.id` (UUID) auf. `epics.external_id` bleibt für externe System-IDs (z.B. YouTrack Issue-Key) reserviert.
> Task-Requests verwenden weiterhin `task_key` (`"TASK-88"`). Das Backend löst den Key intern auf `tasks.id` (UUID) auf; persistente Relationen speichern die UUID-FKs (z.B. `context_boundaries.task_id`, `decision_requests.task_id`).

**`get_prompt` Typen:**

| Typ | Pflicht-Parameter | Beschreibung |
| --- | --- | --- |
| `bibliothekar` | `task_id` | Context Assembly für einen Task |
| `worker` | `task_id` | Worker-Prompt mit Skill + Guards |
| `review` | `task_id` | Owner-Review-Prompt mit DoD + Guard-Status |
| `gaertner` | `task_id` **oder** `epic_id` (mind. eines Pflicht) | Skill-Destillation aus Epic/Task-History |
| `architekt` | `epic_id` | Epic-Decomposition in Tasks |
| `kartograph` | — | Repo-Analyse-Prompt (braucht keinen task/epic Kontext) |
| `triage` | — | Routing-Entscheidung für `[UNROUTED]`-Items — **erfordert `triage`-Permission (admin only)** |

---

## Planer-Writes (Architekt)

```text
hivemind/create_epic          { "project_id": "uuid", "title": "...", "description": "..." }
                                -- Erstellt neues Epic mit state='incoming'; developer in eigenen Projekten, admin überall
hivemind/decompose_epic       { "epic_id": "uuid", "tasks": [...] }
                                -- Tasks werden im State 'scoped' erstellt
hivemind/create_task          { "epic_id": "uuid", "title": "...", "description": "..." }
                                -- Task wird im State 'scoped' erstellt
hivemind/create_subtask       { "parent_task_id": "TASK-88", "title": "..." }
hivemind/link_skill           { "task_id": "TASK-88", "skill_id": "uuid" }
hivemind/set_context_boundary { "task_id": "TASK-88", "allowed_skills": [...], ... }
hivemind/assign_task          { "task_id": "TASK-88", "user_id": "uuid",
                                "assigned_node_id": "uuid" }   -- optional (Phase F): Peer-Node für Delegation
                                -- Setzt assigned_to; löst task_assigned-Notification aus
                                -- Wenn assigned_node_id angegeben: Task.assigned_node_id wird gesetzt,
                                --   Backend broadcastet task_delegated-Event an Peer-Node
                                -- Architekt kann innerhalb eigener Epics zuweisen; Admin überall
hivemind/update_task_state    { "task_id": "TASK-88", "state": "ready" }
                                -- Architekt: scoped → ready (abschließender Schritt nach assign + boundary)
                                -- Backend prüft: assigned_to gesetzt → sonst 422
                                -- Hinweis: derselbe Tool-Name wie in Worker-Writes (s.u.);
                                --   erlaubte Ziel-States sind rollenabhängig (server-seitig enforced):
                                --   als Architekt: scoped → ready
                                --   als Worker:    in_progress → in_review, qa_failed → in_progress
```

---

## Worker-Writes

```text
hivemind/submit_result           { "task_id": "TASK-88", "result": "...", "artifacts": [...] }
                                   -- Speichert Ergebnis + Artefakte; ändert State NICHT
                                   -- Kann jederzeit in in_progress aufgerufen werden

hivemind/update_task_state       { "task_id": "TASK-88", "state": "in_review" }
                                   -- Setzt State auf in_review NUR wenn:
                                   --   (1) submit_result wurde aufgerufen (result vorhanden)
                                   --   (2) Phase 1–4: Keine Guard-Prüfung — Guards dienen als Checkliste, blockieren aber nicht
                                   --   (3) Ab Phase 5: alle Guards status = passed|skipped — sonst 422 mit Liste der offenen Guards
                                   -- Siehe state-machine.md für Phase-basierte Guard-Enforcement-Regeln

hivemind/create_decision_request { "task_id": "TASK-88", "blocker": "...", "options": [...] }
                                   -- Atomar: erstellt decision_request (state='open')
                                   -- und setzt Task in derselben Transaktion von in_progress -> blocked
                                   -- Falls Task nicht in_progress: 409 Conflict
hivemind/report_guard_result     { "task_id": "TASK-88", "guard_id": "uuid",
                                   "status": "passed|failed|skipped",
                                   "result": "..." }    -- Pflicht, nicht-leer für alle Status;
                                                        -- mindestens relevanter Command-Output oder Begründung
```

**Sequenz für in_review-Übergang (verpflichtend):**

```text
1. Worker: hivemind/report_guard_result  → alle Guards auf passed|skipped setzen
2. Worker: hivemind/submit_result        → Ergebnis + Artefakte speichern
3. Worker: hivemind/update_task_state { "state": "in_review" }
             → Backend prüft: Result vorhanden?
             → Phase 1–4: Ja → State → in_review (Guards nicht enforced)
             → Ab Phase 5: Guards vollständig? Result vorhanden?
                → Ja: State → in_review + Notification an Owner
                → Nein: 422 + Liste der offenen Guards / fehlenden Artefakte
```

> **Phase 1–4:** `report_guard_result` ist verfügbar und empfohlen, aber kein technischer Blocker für `in_review`. Guards erscheinen im Review Panel als informative Checkliste für den Owner.
> **Ab Phase 5:** Guard-Enforcement ist technisch aktiv — kein `in_review` ohne `passed|skipped` auf allen Guards.

---

## Gaertner-Writes

```text
hivemind/propose_skill        { "title": "...", "content": "...", "service_scope": [...],
                                "federation_scope": "local|federated" }  -- optional (Phase F), default: 'local'
                                -- Validierung beim Erstellen:
                                --   (1) Circular-Check: schlägt fehl wenn extends-Chain einen Cycle bildet (422)
                                --   (2) Depth-Check: schlägt fehl wenn aufgelöste extends-Kette > 3 Ebenen tief ist (422)
                                --       → Fehlermeldung: "Skill composition exceeds 3 levels. Flatten or split."
                                -- federation_scope im Draft speichern; Admin kann bei merge_skill überschreiben
hivemind/propose_skill_change { "skill_id": "uuid", "diff": "...", "rationale": "..." }
hivemind/fork_federated_skill { "source_skill_id": "uuid",
                                "target_project_id": "uuid|null",
                                "title": "optional override" }
                                -- Erstellt lokalen Fork als neuen Skill (lifecycle='draft', federation_scope='local')
                                -- Parent-Link wird als extends gesetzt (skill_parents: child -> source_skill_id)
                                -- Source bleibt read-only; es wird keine Remote-Entität mutiert
                                -- Erfordert: propose_skill-Permission; Source muss federation_scope='federated' haben
hivemind/submit_skill_proposal { "skill_id": "uuid" }   -- draft → pending_merge
hivemind/create_decision_record { "epic_id": "uuid", "decision": "...", "rationale": "..." }
hivemind/update_doc           { "id": "uuid", "content": "...", "expected_version": 3 }
```

---

## Kartograph-Writes

```text
hivemind/create_wiki_article      { "title": "...", "slug": "...", "content": "...", "tags": [...],
                                    "federation_scope": "local|federated" }  -- optional (Phase F), default: 'local'
hivemind/update_wiki_article      { "id": "uuid", "content": "..." }
hivemind/create_epic_doc          { "epic_id": "uuid", "title": "...", "content": "..." }
hivemind/link_wiki_to_epic        { "article_id": "uuid", "epic_id": "uuid" }
hivemind/propose_epic_restructure { "epic_id": "uuid", "rationale": "...", "proposal": "..." }
hivemind/propose_guard            { "title": "...", "type": "executable", "command": "...",
                                    "scope": [...], "project_id": "uuid|null",
                                    "skill_id": "uuid|null" }
hivemind/propose_guard_change     { "guard_id": "uuid", "diff": "...", "rationale": "..." }
hivemind/submit_guard_proposal    { "guard_id": "uuid" } -- draft → pending_merge

-- Federation (Phase F):
hivemind/start_discovery_session  { "area": "auth/",
                                    "description": "JWT + Session-Handling" }
                                    -- Setzt code_nodes.exploring_node_id für diesen Bereich
                                    -- Broadcastet discovery_session-Event (type='start') an alle Peers
                                    -- Erfordert: kartograph- oder admin-Rolle
hivemind/end_discovery_session    { "area": "auth/" }
                                    -- Räumt exploring_node_id auf (setzt auf NULL)
                                    -- Broadcastet discovery_session-Event (type='end') an alle Peers
                                    -- Erfordert: kartograph- oder admin-Rolle
                                    -- Wird auch automatisch aufgerufen wenn Session > HIVEMIND_DISCOVERY_SESSION_TIMEOUT (default: 4h)
```

---

## Review-Writes (Owner/Admin)

```text
hivemind/approve_review  { "task_id": "TASK-88" }
                           -- in_review → done
                           -- Erfordert: Epic-Owner oder Admin
                           -- Erzeugt Notification: task_done → Assignee + Owner
                           -- Nach done: Gaertner-Prompt wird in Prompt Station bereitgestellt

hivemind/reject_review   { "task_id": "TASK-88",
                           "comment": "..." }
                           -- in_review → qa_failed
                           -- Schreibt task.review_comment; qa_failed_count++
                           -- Backend-Logik: wenn qa_failed_count >= 3 → Task automatisch auf escalated
                           -- Erfordert: Epic-Owner oder Admin
```

> `approve_review` und `reject_review` sind die einzigen Wege aus `in_review`. Kein direktes `done` ohne Review-Gate.
> `reject_review` setzt `qa_failed` — der Worker muss den Kommentar lesen und aktiv `update_task_state { "state": "in_progress" }` aufrufen, um die Arbeit fortzusetzen.

---

## Decision-Writes (Owner/Admin)

```text
hivemind/resolve_decision_request { "id": "uuid", "chosen_option": "A", "comment": "..." }
                                    -- Setzt zugehörigen Task automatisch von blocked → in_progress
                                    -- Erlaubt für: Epic-Owner, Backup-Owner oder admin
```

---

## Admin-Writes

```text
hivemind/assign_bug               { "bug_id": "uuid", "epic_id": "uuid" }
hivemind/merge_skill              { "skill_id": "uuid",           -- lifecycle: pending_merge → active (neuer Skill)
                                    "federation_scope": "local|federated" }  -- optional (Phase F): überschreibt Gaertner-Vorschlag
hivemind/reject_skill             { "skill_id": "uuid",         -- lifecycle: pending_merge → rejected
                                    "reason": "..." }
hivemind/accept_skill_change      { "proposal_id": "uuid" }     -- skill_change_proposals: open → accepted
                                                                 -- wendet diff an → neuer skill_versions-Eintrag
hivemind/reject_skill_change      { "proposal_id": "uuid",      -- skill_change_proposals: open → rejected
                                    "reason": "..." }
hivemind/merge_guard              { "guard_id": "uuid" }        -- lifecycle: pending_merge → active (neuer Guard)
hivemind/reject_guard             { "guard_id": "uuid",         -- lifecycle: pending_merge → rejected
                                    "reason": "..." }
hivemind/accept_guard_change      { "proposal_id": "uuid" }     -- guard_change_proposals: open → accepted
                                                                 -- wendet diff an → aktualisiert guard
hivemind/reject_guard_change      { "proposal_id": "uuid",      -- guard_change_proposals: open → rejected
                                    "reason": "..." }
hivemind/accept_epic_restructure  { "proposal_id": "uuid" }    -- state: open → accepted
hivemind/reject_epic_restructure  { "proposal_id": "uuid",     -- state: open → rejected
                                    "reason": "..." }
hivemind/reassign_epic_owner      { "epic_id": "uuid", "new_owner_id": "uuid" }
hivemind/cancel_task              { "task_id": "TASK-88", "reason": "..." }
hivemind/resolve_escalation       { "task_id": "TASK-88", "comment": "..." }
                                    -- escalated → in_progress (Admin only)
                                    -- Gilt für beide Eskalationsquellen:
                                    --   (a) 3x qa_failed → escalated
                                    --   (b) blocked → escalated (Decision-SLA > 72h)
hivemind/route_event              { "outbox_id": "uuid", "epic_id": "uuid",
                                    "create_as": "task|bug" }     -- Pflicht: bestimmt ob Task oder Bug-Report erzeugt wird
                                    -- sync_outbox.routing_state: unrouted → routed
                                    -- Weist Event dem Epic zu
                                    -- Entscheidungslogik für create_as:
                                    --   "task": bei feature-bezogenen Events (YouTrack Issues, funktionale Anforderungen)
                                    --           → erzeugt neuen Task im Epic (state='incoming')
                                    --   "bug":  bei Fehler-Events (Sentry Exceptions, Crash-Reports, Regressions)
                                    --           → erzeugt node_bug_report + verknüpft mit Epic via epic_node_links
                                    -- Der Admin wählt create_as in der Triage Station explizit;
                                    -- bei Auto-Routing (Phase 7+) entscheidet der Triage-Agent anhand:
                                    --   (1) system='sentry' → default 'bug'
                                    --   (2) system='youtrack' → default 'task'
                                    --   (3) pgvector-Similarity < 0.5 zu bestehenden Tasks → 'task' (neues Thema)
                                    --   (4) pgvector-Similarity >= 0.5 zu bestehendem Bug → 'bug' (Bug-Count erhöhen)
                                    -- Erfordert: triage-Permission (admin only)
hivemind/ignore_event             { "outbox_id": "uuid" }
                                    -- sync_outbox.routing_state: unrouted → ignored
                                    -- Admin entscheidet: Event ist nicht relevant
                                    -- Erfordert: triage-Permission (admin only)
hivemind/requeue_dead_letter      { "id": "uuid" }
                                    -- Requeue für sync_dead_letter:
                                    --   (1) zugehöriger sync_outbox-Eintrag: state -> pending
                                    --   (2) attempts -> 0, next_retry_at -> now()
                                    --   (3) sync_dead_letter.requeued_by/requeued_at wird gesetzt
                                    -- Erfordert: triage-Permission (admin only)
```

> **„Neues Epic anlegen + zuweisen“:** Admin erstellt das Epic via `hivemind/create_epic`, dann ruft er `route_event` mit der neuen `epic_id` auf.

---

## Endpoint-Verhalten (verpflichtend)

- Alle Writes sind **idempotent** (`idempotency_key`)
- Alle mutierenden Writes validieren **`expected_version`** auf der Ziel-Entität (optimistic locking)
- Create-Writes ohne bestehende Ziel-Entität validieren `expected_version` auf der Parent-Entität (z.B. `epic.version` bei `create_task`)
- Antwort enthält immer `audit_id`; bei versionierten Entitäten zusätzlich `new_version`
- Tool-Allowlist je Rolle und je Task-Typ — kein Worker kann Admin-Writes ausführen

---

## Sicherheitsregeln

```json
{
  "request_id": "uuid",
  "actor_id": "uuid",
  "actor_role": "developer|admin|service|kartograph",
  "epic_id": "uuid",        // optional — nur bei Epic/Task-scoped Writes
  "idempotency_key": "uuid",
  "expected_version": 12    // Pflicht für mutierende Writes auf bestehende Entitäten
}
```

> **Trust Boundary — Server-Side Source of Truth:**
> `actor_id` und `actor_role` in diesem Schema dienen als **Dokumentation / Client-Hint** — das Backend extrahiert beide Werte **immer** aus dem JWT/Session-Token und ignoriert bzw. validiert client-seitige Werte dagegen. Client-seitig angegebene `actor_id`/`actor_role` die nicht mit dem Token übereinstimmen → HTTP 403. So ist Spoofing von Actor-Identität oder Rolle ausgeschlossen.

- Kein Write ohne gültigen Actor
- Epic-scoped Writes: Scope-Validierung via `epic_id` (project_member-Check oder Assignee-Check)
- Globale Writes (`merge_skill`, `merge_guard`, `create_wiki_article` etc.): kein `epic_id` erforderlich
- Admin-Writes nur für `admin`
- `resolve_decision_request`: erlaubt für Epic-Owner, Backup-Owner oder `admin`
- Kartograph-Writes nur für `kartograph` und `admin`
- Kontext-Sanitization für externe Payloads (z.B. Sentry Stack Traces)
- Keine ungeprüfte Tool-Ausführung auf Basis von Dokumentinhalt
- Jeder Write erzeugt einen Audit-Eintrag mit Vorher/Nachher-Diff
