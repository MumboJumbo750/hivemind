# Triage — Event-Routing & Entscheidungsstation

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Die Triage ist die **Eingangsschleuse** für alle externen Events die nicht automatisch geroutet werden können. Sie ordnet unklare Ereignisse dem richtigen Epic zu oder erstellt neue Epics.

> Analogie: Eine Notaufnahme-Triage — jedes eingehende Event wird bewertet, priorisiert und dem richtigen Spezialisten zugewiesen.

---

## Kernaufgaben

1. **Event-Routing** — `[UNROUTED]`-Items aus der Sync-Outbox einem Epic zuweisen
2. **Bug-Zuweisung** — Sentry-Events dem verantwortlichen Epic zuordnen
3. **Skill-Proposal-Review** — Pending-Merge-Proposals sichten und Admin-Entscheidung treffen
4. **Dead-Letter-Handling** — Fehlgeschlagene Sync-Einträge requeuen oder verwerfen
5. **Eskalations-Auflösung** — Eskalierte Tasks und Decision Requests bearbeiten

---

## RBAC

Triage erfordert die **`admin`-Rolle**:

| Permission | Beschreibung |
| --- | --- |
| `triage` | `[UNROUTED]`-Items sehen und routen (admin only) |
| `assign_bug` | Bug einem Epic zuweisen |
| `merge_skills` | Skill-Proposals mergen |
| `reject_skill` | Skill-Proposals ablehnen |
| `merge_guard` | Guard-Proposals mergen |
| `reject_guard` | Guard-Proposals ablehnen |
| `manage_epic_restructure` | Restructure-Proposals annehmen/ablehnen |
| `manage_epic_proposals` | Epic-Proposals des Strategen annehmen/ablehnen |
| `cancel_task` | Tasks abbrechen |
| `reassign_owner` | Epic-Owner wechseln |

> "Triage" ist keine eigene RBAC-Rolle, sondern eine **Admin-Funktion**. Nur User mit `role = 'admin'` haben Zugriff auf die Triage Station und können `get_triage` aufrufen. Ab Phase 7 können Admins Triage-Rechte an ausgewählte User delegieren via `app_settings.triage_delegates` (→ [rbac.md — Governance-Delegation](../architecture/rbac.md#governance-delegation--entlastungsmechanik)).

---

## Kategorien in der Triage Station

| Kategorie | Quelle | Aktionen |
| --- | --- | --- |
| `[UNROUTED]` | Webhook-Events mit Confidence < 0.85 | Epic zuweisen (`routing_state → routed`), neues Epic anlegen + zuweisen (`routing_state → routed`), ignorieren (`routing_state → ignored`) |
| `[EPIC PROPOSAL]` | Stratege via `propose_epic` | Akzeptieren (`accept_epic_proposal` → Epic incoming), ablehnen mit Begründung (`reject_epic_proposal`) |
| `[SKILL PROPOSAL]` | Gaertner via `submit_skill_proposal` | Mergen (`merge_skill`), ablehnen mit Begründung (`reject_skill`) |
| `[SKILL CHANGE]` | Gaertner via `propose_skill_change` | Annehmen (`accept_skill_change`), ablehnen mit Begründung (`reject_skill_change`) |
| `[GUARD PROPOSAL]` | Kartograph via `submit_guard_proposal` | Mergen (`merge_guard`), ablehnen mit Begründung (`reject_guard`) |
| `[GUARD CHANGE]` | Kartograph via `propose_guard_change` | Annehmen (`accept_guard_change`), ablehnen mit Begründung (`reject_guard_change`) |
| `[RESTRUCTURE]` | Kartograph via `propose_epic_restructure` | Annehmen (`accept_epic_restructure`), ablehnen mit Begründung (`reject_epic_restructure`) |
| `[DEAD LETTER]` | Outbox nach max Retries | Requeue (`hivemind/requeue_dead_letter`), verwerfen (`hivemind/discard_dead_letter`) |
| `[ESCALATED]` | Tasks mit 3x qa_failed oder Decision-SLA > 72h | Auflösen, Owner wechseln |

---

## Typischer Workflow

```
1. Externes Event kommt via Webhook (YouTrack Issue, Sentry Error)
   → pgvector-Routing: Confidence = 0.71 (< 0.85)
   → Event landet als [UNROUTED] in Triage Station

2. Triage Station zeigt:
   "Sentry: NullPointerException in CartService"
   Vorgeschlagen: EPIC-12 (0.71), EPIC-14 (0.65)
   [→ EPIC-12 ZUWEISEN]  [→ EPIC-14]  [NEU ANLEGEN]  [IGNORIEREN]

3a. Admin: Manuell (UI-Button)
    → Weist Event direkt zu EPIC-12 zu

3b. Admin: Triage-Prompt in AI-Client (für komplexere Fälle)
    → AI analysiert Event-Payload + bestehende Epics
    → AI empfiehlt Routing mit Begründung
    → Admin bestätigt oder überschreibt

4. Event geroutet → routing_state = 'routed'
   → Admin wählt `create_as`: 'task' oder 'bug'
   → 'task': Neuer Task im Ziel-Epic (state='incoming')
   → 'bug': Bug-Report in node_bug_reports + Verknüpfung mit Epic
   → Entscheidungshilfe: Sentry-Events → default 'bug'; YouTrack-Issues → default 'task'
```

---

## Triage-Prompt

Für komplexe Routing-Entscheidungen generiert `get_prompt { "type": "triage" }` einen Prompt:

```
## Rolle: Triage

Du bist verantwortlich für ungeroutete Events.

### Aktuell offene Items
[Liste aller [UNROUTED]-Items mit Payload-Zusammenfassung]

### Aktive Epics
[Liste aller aktiven Epics mit Kurzbeschreibung + Owner]

### Dein Auftrag
Für jedes [UNROUTED]-Item:
1. Bewerte welchem Epic es am besten zugeordnet werden kann
2. Falls kein passendes Epic existiert → empfiehl "Neues Epic anlegen"
3. Begründe deine Entscheidung kurz

### Verfügbare Tools
- hivemind/get_epic       — Epic-Details laden
- hivemind/get_triage     — Aktuelle Triage-Items laden
```

> Der Triage-Prompt erfordert `triage`-Permission (admin only).

---

## MCP-Tools

```text
-- Lesen
hivemind/get_triage              { "state": "unrouted|escalated|dead|all" }

-- UNROUTED Routing
hivemind/route_event             { "outbox_id": "uuid", "epic_id": "EPIC-12",
                                   "create_as": "task|bug" }
                                   -- routing_state: unrouted → routed
hivemind/ignore_event            { "outbox_id": "uuid" }
                                   -- routing_state: unrouted → ignored
hivemind/assign_bug              { "bug_id": "uuid", "epic_id": "EPIC-12" }

-- Dead Letter
hivemind/requeue_dead_letter     { "id": "uuid" }
                                   -- Requeue eines DLQ-Eintrags:
                                   --   sync_outbox.state -> pending
                                   --   attempts -> 0, next_retry_at -> now()
                                   --   sync_dead_letter.requeued_by/requeued_at setzen
hivemind/discard_dead_letter     { "id": "uuid" }
                                   -- Verwirft einen Dead-Letter-Eintrag endgültig:
                                   --   sync_outbox.state bleibt 'dead' (kein Requeue möglich)
                                   --   sync_dead_letter: discarded_by + discarded_at wird gesetzt
                                   --   Audit-Trail bleibt erhalten (kein physisches Löschen)

-- Skill/Guard Proposals (neue Entitäten)
hivemind/merge_skill             { "skill_id": "uuid" }
hivemind/reject_skill            { "skill_id": "uuid", "reason": "..." }
hivemind/merge_guard             { "guard_id": "uuid" }
hivemind/reject_guard            { "guard_id": "uuid", "reason": "..." }

-- Epic Proposals (Stratege)
hivemind/accept_epic_proposal    { "proposal_id": "uuid" }
                                   -- Epic-Proposal → Epic (state: incoming)
                                   -- depends_on-Referenzen auf Proposal-UUIDs werden
                                   -- auf echte Epic-UUIDs aufgelöst
hivemind/reject_epic_proposal    { "proposal_id": "uuid", "reason": "..." }
                                   -- Notification an Strategen mit Begründung
                                   -- Abhängige Proposals erhalten Warnung

-- Skill/Guard Change Proposals (Änderungen an bestehenden Entitäten)
hivemind/accept_skill_change     { "proposal_id": "uuid" }
hivemind/reject_skill_change     { "proposal_id": "uuid", "reason": "..." }
hivemind/accept_guard_change     { "proposal_id": "uuid" }
hivemind/reject_guard_change     { "proposal_id": "uuid", "reason": "..." }

-- Epic Restructure
hivemind/accept_epic_restructure { "proposal_id": "uuid" }
hivemind/reject_epic_restructure { "proposal_id": "uuid", "reason": "..." }

-- Eskalation
hivemind/resolve_escalation      { "task_id": "TASK-88", "comment": "..." }
                                   -- escalated → in_progress (Admin only)
hivemind/reassign_epic_owner     { "epic_id": "EPIC-12", "new_owner_id": "uuid" }
hivemind/cancel_task             { "task_id": "TASK-88", "reason": "..." }
```

---

## Priorisierung

Items in der Triage Station werden nach Dringlichkeit sortiert:

```
Priorität 1: Eskalierte Tasks (SLA überschritten)
Priorität 2: Offene Decision Requests (SLA-Timer läuft)
Priorität 3: [UNROUTED] Events mit Sentry-Severity "fatal"/"error"
Priorität 4: [EPIC PROPOSAL] (Stratege — Planungsblockade wenn nicht reviewed)
Priorität 5: [SKILL PROPOSAL] + [GUARD PROPOSAL] (wartend auf Merge)
Priorität 6: [DEAD LETTER] (fehlgeschlagene Syncs)
Priorität 7: [UNROUTED] Events mit niedrigerer Severity
```

---

## Solo-Modus

Im Solo-Modus führt der Entwickler selbst die Triage durch. Die Triage Station ist vereinfacht — kein Owner-Missing-Problem, da der Solo-User immer Owner ist. Decision-Request-SLAs sind im Solo-Modus deaktiviert.

---

## Abgrenzung

| | Triage | Stratege | Architekt | Kartograph |
| --- | --- | --- | --- | --- |
| Trigger | Externes Event / Proposal / Eskalation | Plan-Dokument vorhanden | Epic gescoppt | Neues Projekt / Follow-up |
| Fokus | Routing & Entscheidung | Strategische Planung | Zerlegung & Zuweisung | Erkundung & Dokumentation |
| Rechte | Admin only | Developer / Admin | Epic-Owner / Admin | Kartograph-Rolle |
| Output | Event-Zuweisung, Merge-Entscheidung, Proposal-Review | Epic-Proposals, Roadmap | Tasks, Boundaries | Wiki, Docs |

---

## Epic-Cancel und offene Items

Wenn ein Epic gecancelt wird, betrifft das auch Triage-relevante Entitäten:

- Offene `decision_requests` (`state = 'open'`) für gecancelte Tasks → `state = 'expired'`; SLA-Timer wird gestoppt
- `[ESCALATED]`-Items für gecancelte Tasks verschwinden aus der Triage Station
- `[UNROUTED]`-Events die bereits geroutet wurden (`routing_state = 'routed'`) bleiben im Audit-Log
