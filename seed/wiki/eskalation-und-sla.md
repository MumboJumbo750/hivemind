---
slug: eskalation-und-sla
title: "Eskalation & SLA — Automatische Deadlines"
tags: [eskalation, sla, decision-request, triage, phase-6]
linked_epics: [EPIC-PHASE-6]
---

# Eskalation & SLA — Automatische Deadlines

Hivemind überwacht Deadlines automatisch und eskaliert bei Verzögerungen — kein Task bleibt unbemerkt liegen.

## SLA-Kaskade

1. **4h vor Deadline** → Notification an Epic-Owner
2. **SLA überschritten** → Notification an Backup-Owner (oder direkt Admins)
3. **24h nach SLA** → Admin-Fallback-Notification

Der SLA-Cron läuft stündlich (konfigurierbar via `HIVEMIND_SLA_CRON_INTERVAL`). Notifications sind idempotent.

## Decision Requests

Wenn ein Worker einen Blocker trifft, erstellt er einen **Decision Request** mit Optionen (A/B/C + Tradeoffs). Der Task wird atomar auf `blocked` gesetzt.

### Decision-SLA-Kaskade
- **24h** → Owner benachrichtigen
- **48h** → Backup-Owner benachrichtigen
- **72h** → System-Automatik: Task → `escalated`, Decision → `expired`, Admins benachrichtigt

Kein automatischer Beschluss — ein Admin muss manuell auflösen.

## 3x qa_failed → Eskalation

Nach dreimaligem Review-Reject (`qa_failed_count >= 3`) wird der Task automatisch auf `escalated` gesetzt. Nur ein Admin kann `escalated → in_progress` auflösen via `hivemind/resolve_escalation`.

## Notification-Modi

- **Phase 2–5:** Client-calculated aus Epic/Task-Daten
- **Ab Phase 6:** Backend-driven. Cutover via `app_settings.notification_mode`
