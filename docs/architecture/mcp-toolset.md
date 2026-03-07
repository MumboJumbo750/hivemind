# MCP Tool-Set

← [Index](../../masterplan.md)

Hivemind ist selbst ein MCP-Server. Alle Tools folgen demselben Sicherheitsmodell: AuthN + AuthZ + Idempotenz + Audit.

**Tool-Naming-Konvention:** Alle Tools verwenden den Namespace-Prefix `hivemind-` gefolgt vom Tool-Namen in `snake_case`. Beispiel: `hivemind-get_task`, `hivemind-create_epic`. Kein Tool verwendet `hm/` oder einen anderen Prefix. Intern (Code, Logs, Audit) wird der volle Name `hivemind-<tool>` verwendet.

---

## Transports

Hivemind implementiert den **MCP 1.0 Standard** (JSON-RPC 2.0 über SSE).

| Transport | Endpoints | Einsatz |
| --- | --- | --- |
| **MCP Standard (SSE)** | `GET /api/mcp/sse` + `POST /api/mcp/message` | Externe MCP-Clients (Cursor, Claude Desktop, Continue) — JSON-RPC 2.0 mit `initialize` Handshake |
| **Convenience REST** | `GET /api/mcp/tools` + `POST /api/mcp/call` | Hivemind-Frontend — einfaches JSON ohne JSON-RPC Overhead |
| **Status** | `GET /api/mcp/status` | Verbindungsstatus, Tool-Count, aktive Sessions |
| **stdio** | Lokaler Prozess | Lokale AI-Clients (optional via `HIVEMIND_TRANSPORT=stdio`) |

Die SSE- und REST-Endpoints sind immer aktiv über denselben FastAPI-Service. Der SDK-basierte `SseServerTransport` aus dem `mcp` Python-Paket (v1.0) wird als raw ASGI-App gemountet.

---

## Read Tools

### Rollen `developer` | `admin` | `kartograph`

```text
hivemind-get_epic           { "id": "uuid" }
hivemind-get_task           { "id": "TASK-88" }         -- task_key, nicht UUID
hivemind-get_skills         { "task_id": "TASK-88" }    -- Bibliothekar-gefiltert
hivemind-get_skill_versions { "skill_id": "uuid" }      -- immutable Versionshistorie
hivemind-list_skills        { "service_scope": [...],    -- optional Filter (z.B. ["backend"])
                              "stack": [...],            -- optional Filter (z.B. ["python"])
                              "lifecycle": "active",     -- optional, default: active
                              "limit": 50, "offset": 0 }
                              -- Browsing aller Skills ohne Task-Bezug
                              -- Stratege nutzt das für Überblick über verfügbare Skills
                              -- Unterschied zu get_skills: kein Bibliothekar-Filtering, kein task_id nötig
hivemind-get_guards         { "task_id": "TASK-88" }    -- alle Guards (global+project+skill+task)
hivemind-get_doc            { "id": "uuid" }
hivemind-get_wiki_article   { "id": "uuid" | "slug": "auth-architektur" }
hivemind-search_wiki        { "query": "authentication", "tags": ["backend"] }
hivemind-get_project_members { "project_id": "uuid" }   -- Gibt alle Member eines Projekts zurück:
                              -- user_id, display_name, role, zugewiesene Epic-Counts
                              -- Stratege nutzt das für Owner-Empfehlung bei propose_epic
hivemind-list_projects      { "limit": 50, "offset": 0 }
hivemind-list_epics         { "project_id": "uuid",     -- Pflicht
                              "state": "...",            -- optional Filter
                              "limit": 50, "offset": 0 }
hivemind-list_tasks         { "epic_id": "EPIC-12",     -- optional (epic_key)
                              "state": "...",            -- optional Filter
                              "assigned_to": "uuid",     -- optional Filter
                              "limit": 50, "offset": 0 }
hivemind-list_peers         { "state": "online|offline|all" }
                              -- Gibt verbundene Peer-Nodes mit Name, Node-ID, Status, letztem Kontakt
                              -- und deren verfügbaren federated Skills zurück
                              -- Erfordert: developer-Rolle (Phase F)
hivemind-list_discovery_sessions { "state": "active|ended|all" }
                              -- Gibt aktive und kürzlich beendete Discovery Sessions zurück:
                              --   area, description, exploring_node_id, started_at, ended_at
                              -- Kartograph nutzt das um Doppelarbeit bei Federation zu vermeiden
                              -- Erfordert: developer|kartograph|admin (Phase F)
hivemind-get_prompt         { "type": "...",            -- Pflicht, siehe unten
                              "task_id": "TASK-88",     -- Pflicht für: bibliothekar, worker, review
                                                        -- optional für: gaertner (mind. eines von task_id/epic_id Pflicht)
                              "epic_id":  "EPIC-12" }   -- epic_key; Pflicht für: architekt
                                                        -- mind. eines von task_id/epic_id Pflicht für: gaertner
                                                        -- optional für: triage, kartograph
```

### Rolle `service` (minimale Scopes)

```text
hivemind-get_epic           { "id": "uuid" }
hivemind-get_task           { "id": "TASK-88" }
```

### Nur Admin (`triage` + `read_audit_log` Permission)

```text
hivemind-get_triage         { "state": "unrouted|escalated|dead|all" }
                              -- Erfordert: triage-Permission (admin only)
                              -- Enthält alle Event-Typen inkl. Federation (Phase F):
                              --   discovery_session (type='start|end'), peer_online, peer_offline,
                              --   federation_error — werden in Triage Station angezeigt

hivemind-get_audit_log      { "epic_id":   "EPIC-12",   -- optional (epic_key)
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

Alle Entitäten haben einen **menschenlesbaren Key** im Format `{PREFIX}-{n}` (PostgreSQL Sequence, immutable).
Zentrale Implementierung: `backend/app/services/key_generator.py`.

| Entität | Identifier | Beispiel | Verwendung in MCP-Tools |
| --- | --- | --- | --- |
| Task | `task_key` (TEXT) | `"TASK-42"` | `task_key`-Parameter in allen Tools (Alias `task_id` wird akzeptiert) |
| Epic | `epic_key` (TEXT) | `"EPIC-12"` | `epic_key`-Parameter in allen Tools (Alias `epic_id` wird akzeptiert) |
| Skill | `skill_key` (TEXT) | `"SKILL-7"` | `skill_key`-Parameter (Legacy: `skill_id` UUID wird weiterhin akzeptiert) |
| Guard | `guard_key` (TEXT) | `"GUARD-3"` | `guard_key`-Parameter (Legacy: `guard_id` UUID wird weiterhin akzeptiert) |
| Wiki | `wiki_key` (TEXT) | `"WIKI-5"` | `wiki_key`-Parameter (alternativ: `slug`) |
| Doc | `doc_key` (TEXT) | `"DOC-8"` | `doc_key`-Parameter |
| User | UUID | `"550e8400-e29b..."` | `actor_id`-Parameter |

> **Unified Key System:** Alle Entity-Keys werden über PostgreSQL Sequences generiert (`{entity}_key_seq`).
> Keys sind **immutable** (DB-Trigger) und **unique**. Sie werden nie recycled.
> API-seitig werden Entitäten per Key referenziert. Das Backend löst den Key intern auf die UUID auf.
> `epics.external_id` / `tasks.external_id` bleiben für externe System-IDs (z.B. YouTrack) reserviert.

**`get_prompt` Typen:**

| Typ | Pflicht-Parameter | Beschreibung |
| --- | --- | --- |
| `bibliothekar` | `task_id` | Context Assembly für einen Task |
| `worker` | `task_id` | Worker-Prompt mit Skill + Guards |
| `review` | `task_id` | Owner-Review-Prompt mit DoD + Guard-Status |
| `gaertner` | `task_id` **oder** `epic_id` (mind. eines Pflicht) | Skill-Destillation aus Epic/Task-History |
| `architekt` | `epic_id` | Epic-Decomposition in Tasks |
| `stratege` | `project_id` | Plan-Analyse, Epic-Ableitung aus Plan-Dokumenten |
| `kartograph` | — | Repo-Analyse-Prompt (braucht keinen task/epic Kontext) |
| `triage` | optional `skill_id` / `guard_id` / `proposal_id` / `decision_id` | Routing- oder Proposal-Entscheidung — **erfordert `triage`-Permission (admin only)** |

---

## Planer-Writes (Stratege & Architekt)

### Stratege-Writes

```text
hivemind-propose_epic         { "project_id": "uuid", "title": "...", "description": "...",
                                "rationale": "...", "suggested_priority": "critical|high|medium|low",
                                "suggested_phase": 1, "depends_on": ["uuid"],
                                "suggested_owner_id": "uuid" }
                                -- Erstellt Epic-Proposal (state: proposed)
                                -- Landet als [EPIC PROPOSAL] in Triage Station
                                -- depends_on: andere epic_proposals.id oder epics.id
                                -- developer in eigenen Projekten, admin überall
hivemind-update_epic_proposal { "proposal_id": "uuid", "title": "...", "description": "..." }
                                -- Proposal nachbessern (nur solange state = proposed)
                                -- Nur der Proposer oder Admin darf ändern
```

### Architekt-Writes

```text
hivemind-create_epic          { "project_id": "uuid", "title": "...", "description": "..." }
                                -- Erstellt neues Epic mit state='incoming'; developer in eigenen Projekten, admin überall
hivemind-decompose_epic       { "epic_key": "EPIC-12", "tasks": [...] }
                                -- Tasks werden im State 'incoming' erstellt
hivemind-create_task          { "epic_key": "EPIC-12", "title": "...", "description": "..." }
                                -- Task wird im State 'incoming' erstellt
hivemind-create_subtask       { "parent_task_key": "TASK-88", "title": "..." }
hivemind-link_skill           { "task_key": "TASK-88", "skill_id": "uuid" }
hivemind-set_context_boundary { "task_key": "TASK-88", "allowed_skills": [...], ... }
hivemind-assign_task          { "task_key": "TASK-88", "user_id": "uuid",
                                "assigned_node_id": "uuid" }   -- optional (Phase F): Peer-Node für Delegation
                                -- Setzt assigned_to; löst task_assigned-Notification aus
                                -- Wenn assigned_node_id angegeben: Task.assigned_node_id wird gesetzt,
                                --   Backend broadcastet task_delegated-Event an Peer-Node
                                -- Architekt kann innerhalb eigener Epics zuweisen; Admin überall
hivemind-update_task_state    { "task_key": "TASK-88", "target_state": "ready" }
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
hivemind-submit_result           { "task_key": "TASK-88", "result": "...", "artifacts": [...] }
                                   -- Speichert Ergebnis + Artefakte; ändert State NICHT
                                   -- Kann jederzeit in in_progress aufgerufen werden

hivemind-update_task_state       { "task_key": "TASK-88", "target_state": "in_review" }
                                   -- Setzt State auf in_review NUR wenn:
                                   --   (1) submit_result wurde aufgerufen (result vorhanden)
                                   --   (2) Phase 1–4: Keine Guard-Prüfung — Guards dienen als Checkliste, blockieren aber nicht
                                   --   (3) Ab Phase 5: alle Guards status = passed|skipped — sonst 422 mit Liste der offenen Guards
                                   -- Siehe state-machine.md für Phase-basierte Guard-Enforcement-Regeln

hivemind-create_decision_request { "task_key": "TASK-88", "question": "...", "options": [...] }
                                   -- Atomar: erstellt decision_request (state='open')
                                   -- und setzt Task in derselben Transaktion von in_progress -> blocked
                                   -- Falls Task nicht in_progress: 409 Conflict
hivemind-report_guard_result     { "task_key": "TASK-88", "guard_id": "uuid",
                                   "status": "passed|failed|skipped",
                                   "result": "..." }    -- Pflicht, nicht-leer für alle Status;
                                                        -- mindestens relevanter Command-Output oder Begründung
```

**Sequenz für in_review-Übergang (verpflichtend):**

```text
1. Worker: hivemind-report_guard_result  → alle Guards auf passed|skipped setzen
2. Worker: hivemind-submit_result        → Ergebnis + Artefakte speichern
3. Worker: hivemind-update_task_state { "target_state": "in_review" }
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
hivemind-propose_skill        { "title": "...", "content": "...", "service_scope": [...],
                                "federation_scope": "local|federated" }  -- optional (Phase F), default: 'local'
                                -- Validierung beim Erstellen:
                                --   (1) Circular-Check: schlägt fehl wenn extends-Chain einen Cycle bildet (422)
                                --   (2) Depth-Check: schlägt fehl wenn aufgelöste extends-Kette > 3 Ebenen tief ist (422)
                                --       → Fehlermeldung: "Skill composition exceeds 3 levels. Flatten or split."
                                -- federation_scope im Draft speichern; Admin kann bei merge_skill überschreiben
hivemind-propose_skill_change { "skill_id": "uuid", "diff": "...", "rationale": "..." }
hivemind-fork_federated_skill { "source_skill_id": "uuid",
                                "target_project_id": "uuid|null",
                                "title": "optional override" }
                                -- Erstellt lokalen Fork als neuen Skill (lifecycle='draft', federation_scope='local')
                                -- Parent-Link wird als extends gesetzt (skill_parents: child -> source_skill_id)
                                -- Source bleibt read-only; es wird keine Remote-Entität mutiert
                                -- Erfordert: propose_skill-Permission; Source muss federation_scope='federated' haben
hivemind-submit_skill_proposal { "skill_id": "uuid" }   -- draft → pending_merge
                                   -- Nach submit_skill_proposal: bei governance.skill_merge != manual
                                   --   dispatcht der Conductor triage_skill_proposal
hivemind-create_decision_record { "epic_id": "EPIC-12", "decision": "...", "rationale": "..." }
hivemind-update_doc           { "id": "uuid", "content": "...", "expected_version": 3 }
```

---

## Kartograph-Writes

```text
hivemind-create_epic_doc          { "epic_id": "EPIC-12", "title": "...", "content": "..." }
hivemind-link_wiki_to_epic        { "article_id": "uuid", "epic_id": "EPIC-12" }
hivemind-propose_epic_restructure { "restructure_type": "split|merge|task_move",
                                    "payload": { ... },         -- Typ-spezifisch: Split/Merge/Task-Move-Spec
                                    -- Split:     { "source_epic_id": "EPIC-5", "resulting_epics": [...] }
                                    -- Merge:     { "source_epic_ids": ["EPIC-8", "EPIC-9"], "resulting_epic": {...} }
                                    -- Task-Move: { "moves": [{ "task_key": "TASK-15", "from_epic_key": "EPIC-5", "to_epic_key": "EPIC-6" }] }
                                    "rationale": "string",
                                    "code_node_refs": ["uuid", "..."] }
                                    -- → Vollständige Payload-Specs: docs/features/epic-restructure.md#proposal-typen
hivemind-propose_guard            { "title": "...", "type": "executable", "command": "...",
                                    "scope": [...], "project_id": "uuid|null",
                                    "skill_id": "uuid|null" }
hivemind-propose_guard_change     { "guard_id": "uuid", "diff": "...", "rationale": "..." }
hivemind-submit_guard_proposal    { "guard_id": "uuid" } -- draft → pending_merge
                                    -- Nach submit_guard_proposal: bei governance.guard_merge != manual
                                    --   dispatcht der Conductor triage_guard_proposal

-- Federation (Phase F):
hivemind-start_discovery_session  { "area": "auth/",
                                    "description": "JWT + Session-Handling" }
                                    -- Setzt code_nodes.exploring_node_id für diesen Bereich
                                    -- Broadcastet discovery_session-Event (type='start') an alle Peers
                                    -- Erfordert: kartograph- oder admin-Rolle
hivemind-end_discovery_session    { "area": "auth/" }
                                    -- Räumt exploring_node_id auf (setzt auf NULL)
                                    -- Broadcastet discovery_session-Event (type='end') an alle Peers
                                    -- Erfordert: kartograph- oder admin-Rolle
                                    -- Wird auch automatisch aufgerufen wenn Session > HIVEMIND_DISCOVERY_SESSION_TIMEOUT (default: 4h)
```

---

## Wiki-Writes (Kartograph, Stratege, Admin)

```text
hivemind-create_wiki_article      { "title": "...", "slug": "...", "content": "...", "tags": [...],
                                    "federation_scope": "local|federated" }  -- optional (Phase F), default: 'local'
                                    -- Erfordert: developer|kartograph|admin
                                    -- Kartograph: Code-Dokumentation, Architektur-Wiki
                                    -- Stratege: Roadmap, Dependency-Dokumentation, strategische Wiki-Artikel
hivemind-update_wiki_article      { "id": "uuid", "content": "..." }
                                    -- Erfordert: developer|kartograph|admin
```

> **Warum Wiki-Writes für developer?** Der Stratege (developer-Rolle) erstellt Roadmap- und Strategy-Wiki-Artikel. Der Kartograph (kartograph-Rolle) erstellt Code-Dokumentation. Beide brauchen Wiki-Schreibzugriff. Die Tools sind daher nicht auf eine einzelne Rolle beschränkt.

---

## Memory-Writes (Cross-Agent)

Alle Memory-Tools sind für **jeden authentifizierten Agenten** verfügbar (`developer|kartograph|admin`). Das Memory Ledger ist ein Cross-Cutting System Skill — vollständige Spezifikation: [Memory Ledger](../features/memory-ledger.md).

```text
-- Lesen
hivemind-get_memory_context     { "scope": "project|epic|task",
                                  "scope_id": "uuid" }
                                  -- Liefert: aktuellste L2-Summaries + L1-Fakten + offene Fragen
                                  -- + Integrity-Warnungen (unbedeckte L0-Entries)
                                  -- Typisch: Session-Resume (erst Kontext laden, dann arbeiten)

hivemind-search_memories        { "query": "...",
                                  "scope": "project|epic|task",   -- optional
                                  "scope_id": "uuid",             -- optional
                                  "level": "L0|L1|L2|all",       -- optional, default: all
                                  "tags": [...] }                  -- optional Filter
                                  -- pgvector-Similarity-Search über Memory Entries
                                  -- Gaertner nutzt: search_memories { "query": "skill-candidate" }

hivemind-get_open_questions     { "scope": "project|epic|task",
                                  "scope_id": "uuid" }
                                  -- Alle offenen Fragen aus L2-Summaries für diesen Scope
                                  -- Agenten priorisieren: offene Fragen zuerst klären

hivemind-get_uncovered_entries  { "scope": "project|epic|task",
                                  "scope_id": "uuid" }
                                  -- L0-Entries die noch von keiner L2-Summary abgedeckt sind
                                  -- Integrity-Check: sollten bei nächster Kompaktierung berücksichtigt werden

-- Schreiben
hivemind-save_memory            { "scope": "project|epic|task",
                                  "scope_id": "uuid",
                                  "content": "...",
                                  "tags": [...] }                  -- optional; reserviert: "skill-candidate"
                                  -- Erstellt L0 Memory Entry (append-only, immutable)
                                  -- Automatisch: embedding via nomic-embed-text für Similarity-Search

hivemind-extract_facts          { "entry_ids": ["uuid"],
                                  "facts": [
                                    { "entity": "auth/jwt", "key": "algorithm", "value": "RS256" }
                                  ] }
                                  -- Erstellt L1 Extracted Facts aus L0-Entries
                                  -- Strukturierte Schlüsselfakten die jede Verdichtung überleben
                                  -- Empfehlung: vor compact_memories aufrufen

hivemind-compact_memories       { "entry_ids": ["uuid", "..."],
                                  "summary": "...",
                                  "open_questions": ["..."] }      -- optional
                                  -- Erstellt L2 Session Summary aus einer Gruppe von L0-Entries
                                  -- source_entry_ids + source_fact_ids werden für Coverage-Tracking gespeichert
                                  -- L0-Entries werden NICHT gelöscht (append-only)

hivemind-graduate_memory        { "summary_id": "uuid",
                                  "target": "wiki|skill|doc",
                                  "target_id": "uuid" }
                                  -- Markiert L2-Summary als graduated (wird nicht mehr bei Resume geladen)
                                  -- Ziel-Entität (Wiki/Skill/Doc) übernimmt das Wissen dauerhaft
                                  -- L0/L1-Daten bleiben als Audit-Trail bestehen
```

---

## Reviewer-Writes (Phase 8)

```text
hivemind-submit_review_recommendation
                         { "task_key": "TASK-88",
                           "recommendation": "approve|reject|needs_human_review",
                           "confidence": 0.92,
                           "summary": "Alle DoD-Kriterien erfüllt, Guards passed, Code-Qualität gut",
                           "checklist": [
                             { "criterion": "Endpoint liefert 200", "met": true },
                             { "criterion": "Error-Handling vorhanden", "met": true }
                           ],
                           "concerns": [] }
                           -- Speichert AI-Review-Empfehlung in review_recommendations Tabelle
                           -- Erfordert: Rolle reviewer (nur Reviewer-Agent)
                           -- Triggert NICHT approve/reject — nur Empfehlung
                           -- Bei Governance auto + Confidence ≥ Threshold: Conductor ruft approve_review auf
                           -- Bei Governance assisted: Owner sieht Empfehlung mit 1-Click-Bestätigung
                           -- Bei Governance manual: Nicht dispatcht (kein Reviewer-Prompt)
```

> `submit_review_recommendation` ist **read-only gegenüber Task-State** — die Empfehlung ändert nie direkt den Task-Status. Nur `approve_review` und `reject_review` können das.

---

## Review-Writes (Owner/Admin)

```text
hivemind-approve_review  { "task_key": "TASK-88" }
                           -- in_review → done
                           -- Erfordert: Epic-Owner oder Admin
                           -- Erzeugt Notification: task_done → Assignee + Owner
                           -- Nach done: identischer Folgepfad fuer manuell und auto-approve,
                           --   inkl. Gaertner-Dispatch

hivemind-reject_review   { "task_key": "TASK-88",
                           "comment": "..." }
                           -- in_review → qa_failed
                           -- Schreibt task.review_comment; qa_failed_count++
                           -- Triggert task_qa_failed → Gaertner Review-Feedback-Loop
                           -- Hinweis: reject_review setzt IMMER auf qa_failed, nie direkt auf escalated.
                           --   Eskalation greift erst wenn der Worker danach in_progress anfordert
                           --   und qa_failed_count >= 3 ist (→ state-machine.md).
                           -- Erfordert: Epic-Owner oder Admin
```

> `approve_review` und `reject_review` sind die einzigen Wege aus `in_review`. Kein direktes `done` ohne Review-Gate.
> `reject_review` setzt `qa_failed` — der Worker muss den Kommentar lesen und aktiv `update_task_state { "target_state": "in_progress" }` aufrufen, um die Arbeit fortzusetzen.

> **Param-Alias-Toleranz:** Das Backend akzeptiert gängige Alias-Parameter automatisch: `task_id` → `task_key`, `epic_id` → `epic_key`, `state` → `target_state`, `assignee_id` → `user_id`, `result_text` → `result`, `blocker` → `question`, `chosen_option` → `decision`, `id` → `decision_request_id`. Die kanonischen Namen (links der Tabelle) sind bevorzugt.

---

## Decision-Writes (Owner/Admin)

```text
hivemind-resolve_decision_request { "decision_request_id": "uuid", "decision": "A", "rationale": "..." }
                                    -- Setzt zugehörigen Task automatisch von blocked → in_progress
                                    -- Erlaubt für: Epic-Owner, Backup-Owner oder admin
```

---

## Admin-Writes

```text
hivemind-assign_bug               { "bug_id": "uuid", "epic_id": "EPIC-12" }
hivemind-merge_skill              { "skill_id": "uuid",           -- lifecycle: pending_merge → active (neuer Skill)
                                    "federation_scope": "local|federated" }  -- optional (Phase F): überschreibt Gaertner-Vorschlag
hivemind-reject_skill             { "skill_id": "uuid",         -- lifecycle: pending_merge → rejected
                                    "reason": "..." }
hivemind-accept_skill_change      { "proposal_id": "uuid" }     -- skill_change_proposals: open → accepted
                                                                 -- wendet diff an → neuer skill_versions-Eintrag
hivemind-reject_skill_change      { "proposal_id": "uuid",      -- skill_change_proposals: open → rejected
                                    "reason": "..." }
hivemind-merge_guard              { "guard_id": "uuid" }        -- lifecycle: pending_merge → active (neuer Guard)
hivemind-reject_guard             { "guard_id": "uuid",         -- lifecycle: pending_merge → rejected
                                    "reason": "..." }
hivemind-accept_guard_change      { "proposal_id": "uuid" }     -- guard_change_proposals: open → accepted
                                                                 -- wendet diff an → aktualisiert guard
hivemind-reject_guard_change      { "proposal_id": "uuid",      -- guard_change_proposals: open → rejected
                                    "reason": "..." }
hivemind-accept_epic_restructure  { "proposal_id": "uuid" }    -- state: proposed → accepted
hivemind-reject_epic_restructure  { "proposal_id": "uuid",     -- state: proposed → rejected
                                    "reason": "..." }
hivemind-apply_epic_restructure   { "proposal_id": "uuid" }    -- state: accepted → applied
                                    -- Führt die Restrukturierung atomar aus (Split/Merge/Task-Move)
                                    -- Validiert: alle betroffenen Tasks in verschiebbarem State
                                    -- Bei blockierenden Tasks (in_progress/in_review): HTTP 422 mit blocking_tasks-Liste
                                    -- Erzeugt neue Epics (Split), verschiebt Tasks, cancelt Source-Epics (Merge)
                                    -- Erfordert: admin oder manage_epic-Berechtigung
                                    -- → Vollständiger Apply-Flow: docs/features/epic-restructure.md#apply-flow--end-to-end
hivemind-accept_epic_proposal     { "proposal_id": "uuid" }    -- epic_proposals: proposed → accepted
                                    -- Erstellt Epic (state: incoming) mit Daten aus Proposal
                                    -- Setzt epic_proposals.resulting_epic_id auf das neue Epic
                                    -- Löst depends_on-Referenzen auf echte Epic-UUIDs auf
                                    -- Notification an Proposer: "Epic Proposal akzeptiert"
hivemind-reject_epic_proposal     { "proposal_id": "uuid",     -- epic_proposals: proposed → rejected
                                    "reason": "..." }
                                    -- Notification an Proposer mit Begründung
                                    -- Wenn andere Proposals depends_on dieses Proposal referenzieren:
                                    --   Warnung an Proposer: "Abhängiges Proposal abgelehnt"
hivemind-reassign_epic_owner      { "epic_key": "EPIC-12", "owner_id": "uuid" }
hivemind-cancel_task              { "task_key": "TASK-88", "reason": "..." }
hivemind-resolve_escalation       { "task_key": "TASK-88", "comment": "..." }
                                    -- escalated → in_progress (Admin only)
                                    -- Gilt für beide Eskalationsquellen:
                                    --   (a) 3x qa_failed → escalated
                                    --   (b) blocked → escalated (Decision-SLA > 72h)
hivemind-route_event              { "outbox_id": "uuid", "epic_id": "EPIC-12",
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
hivemind-ignore_event             { "outbox_id": "uuid" }
                                    -- sync_outbox.routing_state: unrouted → ignored
                                    -- Admin entscheidet: Event ist nicht relevant
                                    -- Erfordert: triage-Permission (admin only)
hivemind-requeue_dead_letter      { "id": "uuid" }
                                    -- Requeue für sync_dead_letter:
                                    --   (1) zugehöriger sync_outbox-Eintrag: state -> pending
                                    --   (2) attempts -> 0, next_retry_at -> now()
                                    --   (3) sync_dead_letter.requeued_by/requeued_at wird gesetzt
                                    -- Erfordert: triage-Permission (admin only)
hivemind-discard_dead_letter      { "id": "uuid" }
                                    -- Verwirft einen Dead-Letter-Eintrag endgültig:
                                    --   (1) zugehöriger sync_outbox-Eintrag: state bleibt 'dead' (kein Requeue möglich)
                                    --   (2) sync_dead_letter: discarded_by + discarded_at wird gesetzt
                                    --   (3) Audit-Trail bleibt erhalten (kein physisches Löschen)
                                    -- Erfordert: triage-Permission (admin only)
```

> **„Neues Epic anlegen + zuweisen“:** Admin erstellt das Epic via `hivemind-create_epic`, dann ruft er `route_event` mit der neuen `epic_id` auf.

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
  "actor_role": "developer|admin|service|kartograph|reviewer",
  "epic_id": "EPIC-12",     // optional — epic_key; nur bei Epic/Task-scoped Writes
  "idempotency_key": "uuid",
  "expected_version": 12    // Pflicht für mutierende Writes auf bestehende Entitäten
}
```

> **Trust Boundary — Server-Side Source of Truth:**
> `actor_id` und `actor_role` in diesem Schema dienen als **Dokumentation / Client-Hint** — das Backend extrahiert beide Werte **immer** aus dem JWT/Session-Token und ignoriert bzw. validiert client-seitige Werte dagegen. Client-seitig angegebene `actor_id`/`actor_role` die nicht mit dem Token übereinstimmen → HTTP 403. So ist Spoofing von Actor-Identität oder Rolle ausgeschlossen.

- Kein Write ohne gültigen Actor
- Epic-scoped Writes: Scope-Validierung via `epic_id` (project_member-Check oder Assignee-Check)
- Globale Writes (`merge_skill`, `merge_guard` etc.): kein `epic_id` erforderlich
- Admin-Writes nur für `admin`
- `resolve_decision_request`: erlaubt für Epic-Owner, Backup-Owner oder `admin`
- Wiki-Writes (`create_wiki_article`, `update_wiki_article`) für `developer`, `kartograph` und `admin`
- Kartograph-Writes (Epic-Docs, Guards, Restructure, Discovery Sessions) nur für `kartograph` und `admin`
- Memory-Writes (alle `*_memory`, `extract_facts`, `compact_memories`, `graduate_memory`) für `developer`, `kartograph` und `admin`
- Reviewer-Writes (`submit_review_recommendation`) nur für `reviewer` — kann Task-State nicht direkt ändern
- Kontext-Sanitization für externe Payloads (z.B. Sentry Stack Traces)
- Keine ungeprüfte Tool-Ausführung auf Basis von Dokumentinhalt
- Jeder Write erzeugt einen Audit-Eintrag mit Vorher/Nachher-Diff
