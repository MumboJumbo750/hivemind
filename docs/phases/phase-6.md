# Phase 6 — Eskalation & Triage

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** SLA-Automation, Eskalations-Flow, Decision Requests, Backup-Owner, Admin-Fallback.

**AI-Integration:** Weiterhin manuell. Triage-Prompt für Routing-Entscheidungen.

---

## Deliverables

### Backend

- [ ] SLA-Cron-Job: prüft Deadlines, triggert Notifications
  - Laufintervall: **stündlich** (mindestens) — 4h-SLA-Warnung erfordert Stunden-Granularität
  - 4h vor SLA → Notification an Owner
  - SLA überschritten → Notification an Backup-Owner (bei `backup_owner_id = NULL` → direkt Admins)
  - 24h nach SLA → Admin-Fallback-Notification (Epic weiterhin priorisiert in Triage)
- [ ] Decision-Request-SLA-Enforcement:
  - 24h → Owner benachrichtigen
  - 48h → Backup-Owner benachrichtigen (bei `backup_owner_id = NULL` → Schritt überspringen)
  - 72h → **System-Automatik:** Task `blocked → escalated`; Decision Request `state → expired`; alle Admins erhalten Notification (`decision_escalated_admin`) — kein automatischer Beschluss; Admin löst `escalated` danach manuell auf
- [ ] Decision-Write:
  - `hivemind/resolve_decision_request` — Decision Request auflösen (Owner oder Admin; Admin immer erlaubt)
- [ ] Admin-Writes:
  - `hivemind/reassign_epic_owner` — Owner wechseln
  - `hivemind/assign_bug` — Bug zu Epic zuweisen
- [ ] Eskalations-Logik: nach 3x `qa_failed` → Task auf `escalated`
- [ ] Triage-Prompt-Generator für `[UNROUTED]`-Items
- [ ] Notification-Service (in-DB, kein externer Service): schreibt in `notifications`-Tabelle

### Frontend

- [ ] Decision-Request-Dialog:
  - Modal mit Optionen A/B/C und Tradeoffs
  - SLA-Timer sichtbar
  - "Option wählen + Begründung" → `resolve_decision_request`
- [ ] Eskalations-Ansicht in Triage Station:
  - `[ESCALATED]`-Kategorie
  - Priorisiert nach SLA-Überschreitung
  - Admin-Resolve-Button
- [ ] SLA-Timer animiert (Countdown, Farbe: grün → amber → rot)
- [ ] Notification Tray: alle Notification-Typen implementiert
- [ ] Notification Tray als Action Queue gruppiert:
  - `ACTION NOW` (kritisch)
  - `SOON` (zeitnah)
  - `FYI` (informativ)
  - pro Eintrag: Typ, Zeit, Grund, naechste Aktion
- [ ] Backup-Owner-Anzeige auf Epics + Decision Requests

---

## Eskalations-Flow

```text
Task in_progress
  ├─ 3x qa_failed ──────────────────────────────────────→ escalated
  │                                                           │
  ├─ Worker: create_decision_request                          │
  │   ├─ 24h → Owner Notification                            │
  │   ├─ 48h → Backup-Owner Notification                    │
  │   └─ 72h → Admin-Fallback                               │
  │                                                           │
  └─ Owner/Admin: resolve_decision_request ───────────→ in_progress
```

---

## Acceptance Criteria

- [ ] Cron-Job läuft stündlich (konfigurierbar via `HIVEMIND_SLA_CRON_INTERVAL`)
- [ ] SLA-Notification erscheint 4h vor Deadline in Notification Tray
- [ ] Decision Request eskaliert nach 72h ohne Auflösung
- [ ] `escalated`-Tasks erscheinen priorisiert in Triage Station
- [ ] `hivemind/resolve_escalation` setzt `escalated → in_progress` (Admin only)
- [ ] `hivemind/resolve_decision_request` löst Decision Request auf und setzt Task automatisch `blocked → in_progress`
- [ ] Epic-Cancel: offene `decision_requests` werden auf `expired` gesetzt; SLA-Timer gestoppt
- [ ] `hivemind/route_event` setzt `routing_state → routed` und weist Event dem Epic zu (implementiert in Phase 3)
- [ ] `hivemind/ignore_event` setzt `routing_state → ignored` (implementiert in Phase 3)
- [ ] Backup-Owner-Feld auf Epics ist editierbar (Admin)
- [ ] SLA-Timer auf Epic-Cards färbt sich korrekt (grün → amber → rot)
- [ ] Notification Tray gruppiert Eintraege korrekt in `ACTION NOW`, `SOON`, `FYI`
- [ ] Notification-Eintraege zeigen "warum" und "naechste Aktion" nachvollziehbar an

---

## Notification-Typen und Routing

Alle Notification-Typen und wer sie empfängt:

| Typ | Auslöser | Empfänger |
| --- | --- | --- |
| `sla_warning` | 4h vor SLA-Fälligkeit | Epic-Owner |
| `sla_breach` | SLA überschritten | Epic-Backup-Owner |
| `decision_request` | Worker erstellt Decision Request | Epic-Owner |
| `decision_escalated_backup` | 48h ohne Auflösung | Epic-Backup-Owner |
| `decision_escalated_admin` | 72h ohne Auflösung | Alle Admins |
| `escalation` | Task nach 3x qa_failed eskaliert | Epic-Owner + Admins |
| `skill_proposal` | Gaertner hat Skill-Proposal eingereicht | Alle Admins |
| `skill_merged` | Admin merged ein Skill-Proposal | Skill-Proposer + Admins |
| `task_done` | Task wurde in Review genehmigt (`done`) | Assigned-Worker + Epic-Owner |
| `dead_letter` | Sync-Eintrag wurde in DLQ verschoben | Alle Admins |
| `guard_failed` | Guard-Result `failed` gemeldet | Assigned-Worker + Epic-Owner |
| `task_assigned` | Task wird einem User zugewiesen | Neuer Assignee |
| `review_requested` | Task geht in `in_review` | Epic-Owner |

**Routing-Logik:**

- Owner und Backup-Owner aus `epics.owner_id` / `epics.backup_owner_id`
- Admins = alle User mit `role = 'admin'`
- Solo-Modus: alle Notifications gehen an den System-User (kein Routing nötig)
- **`backup_owner_id = NULL`:** `sla_breach` und `decision_escalated_backup` werden übersprungen — Admins empfangen diese Notifications direkt beim nächsten SLA-Schritt

→ Notification-Schema: [data-model.md](../architecture/data-model.md) — Tabelle `notifications` (angelegt in Phase 1, befüllt ab Phase 6)

---

## Abhängigkeiten

- Phase 5 abgeschlossen (Worker & Gaertner Writes)

## Öffnet folgende Phase

→ [Phase 7: Integration Hardening](./phase-7.md)
