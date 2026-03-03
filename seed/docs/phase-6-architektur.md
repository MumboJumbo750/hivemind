---
epic_ref: "EPIC-PHASE-6"
title: "Phase 6 — Architektur-Kontext"
---

# Phase 6 — Eskalation & Triage

## Überblick

Phase 6 liefert SLA-Automation, den Eskalations-Flow, Decision Requests mit SLA-Enforcement, Backup-Owner-Logik und den vollständigen Notification-Service.

## Architektur-Entscheidungen

### SLA-Cron statt Echtzeit-Trigger
Stündlicher Cron-Job (konfigurierbar: `HIVEMIND_SLA_CRON_INTERVAL`) statt Event-basierter SLA-Prüfung. Vorteil: einfach, idempotent, kein Race-Condition-Risiko. Nachteil: max. 1h Verzögerung — mitigierbar durch 15-Min-Intervall.

### Decision-Request-SLA-Kaskade
Dreistufig: 24h → Owner, 48h → Backup-Owner, 72h → System-Automatik (Task → `escalated`, Decision → `expired`, Admins benachrichtigt). Kein automatischer Beschluss — Admin löst manuell.

### In-DB Notification-Service
Notifications werden in der `notifications`-Tabelle gespeichert (kein externer Service). Client erkennt via `GET /api/settings { notification_mode }` ob client-calculated (Phase 2–5) oder backend-driven (ab Phase 6) aktiv ist. Cutover bei Phase-6-Alembic-Migration.

### 3x qa_failed → Eskalation
Nach dreimaligem Review-Reject wird der Task automatisch auf `escalated` gesetzt. Nur Admin kann `escalated → in_progress` auflösen.

## Eskalations-Flow

```
Task in_progress
  ├─ 3x qa_failed ──────────────────→ escalated
  ├─ Worker: create_decision_request
  │   ├─ 24h → Owner Notification
  │   ├─ 48h → Backup-Owner Notification
  │   └─ 72h → Admin-Fallback (escalated)
  └─ Owner/Admin: resolve ──────────→ in_progress
```

## Notification-Typen

| Typ | Empfänger |
| --- | --- |
| `sla_warning` | Epic-Owner |
| `sla_breach` | Epic-Backup-Owner / Admins |
| `decision_request` | Epic-Owner |
| `decision_escalated_admin` | Alle Admins |
| `escalation` | Epic-Owner + Admins |
| `skill_proposal` / `skill_merged` | Admins / Proposer |
| `task_done` | Worker + Epic-Owner |
| `dead_letter` | Admins |
| `guard_failed` | Worker + Epic-Owner |
| `task_assigned` | Neuer Assignee |
| `review_requested` | Epic-Owner |

## Relevante Skills
- `scheduled-job` — APScheduler Cron-Job
- `decision-request` — Decision-Request-Lifecycle
- `notification-dispatch` — Notification-Service
- `state-machine-transition` — State-Transitions
- `fastapi-endpoint` — Endpoint-Erstellung
- `vue-component` — Vue 3 Component-Pattern
