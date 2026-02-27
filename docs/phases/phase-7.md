# Phase 7 — Externe Integration Hardening

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** YouTrack/Sentry-Integration robust machen. Outbox-Consumer, DLQ-UI, pgvector-Routing aktivieren, Bug Heatmap.

**AI-Integration:** Weiterhin manuell. pgvector-Routing jetzt automatisch (erster echter Auto-Routing-Schritt).

---

## Deliverables

### Backend

- [ ] Outbox-Consumer für `outbound` (YouTrack/Sentry): verarbeitet `sync_outbox` mit Exponential Backoff (`direction='outbound'`)
  - **Kontext:** Seit Phase 3 schreibt der Webhook-Ingest `inbound`-Events in `sync_outbox`. **Falls Phase F vor Phase 7 abgeschlossen wurde:** der `peer_outbound`-Consumer für Federation existiert bereits — Phase 7 ergänzt nur den `outbound`-Consumer. **Falls Phase F noch nicht implementiert wurde:** Phase 7 implementiert beide Consumer zusammen (`outbound` + `peer_outbound`). Phase 7 aktiviert außerdem Routing für `inbound`-Events.
  - `next_retry_at = now() + 2^attempts * 60s`
  - Nach `attempts >= HIVEMIND_DLQ_MAX_ATTEMPTS (5)` → in `sync_dead_letter`
- [ ] YouTrack-Sync: Status-Updates + Assignee rücksyncen
- [ ] Sentry-Sync: Bug-Reports aggregieren in `node_bug_reports`
- [ ] pgvector-Routing: Epic-Embeddings verwenden für Auto-Routing
  - Confidence >= 0.85 → auto-assign
  - Confidence < 0.85 → `[UNROUTED]`
- [ ] Admin-Tool: `hivemind/assign_bug` — manuelles Bug→Epic Routing (hier implementiert, **nicht** in Phase 6 — erst Phase 7 hat Sentry-Daten)
- [ ] Audit-Retention-Cron: bereinigt alte `input_payload`/`output_payload`
- [ ] DLQ-Requeue als MCP-Tool: `hivemind/requeue_dead_letter { "id": "uuid" }` (admin + triage permission)
- [ ] Optionaler REST-Alias: `POST /api/triage/dead-letters/{id}/requeue` ruft intern denselben Requeue-Service auf
- [ ] Embedding-Neuberechnung: wenn Embedding-Provider gewechselt wird

### Frontend
- [ ] Nexus Grid: Bug-Heatmap aktivieren
  - Knotengröße und -farbe nach `node_bug_reports.count`
  - Hover: Bug-Details Panel
- [ ] Triage Station: `[DEAD LETTER]`-Kategorie
  - Fehler-Details anzeigen
  - "Erneut versuchen"-Button → Requeue
- [ ] Sync-Status-Panel in Settings:
  - Outbox-Queue-Größe
  - Letzte erfolgreiche Syncs
  - Fehlgeschlagene Syncs mit Details
- [ ] KPI-Dashboard (erster Stand): Routing-Precision, SLA-Erfüllung
- [ ] Performance-Budget fuer schwere Views dokumentiert und geprueft:
  - Nexus Grid (inkl. Bug-Heatmap)
  - Triage-Listen (inkl. Dead Letter)

---

## pgvector-Routing Aktivierung

```text
# Phase 1-2: Kein Routing, alles [UNROUTED]
# Phase 3: Webhook-Ingest schreibt inbound in sync_outbox
# Phase 7: Outbox-Consumer für outbound startet + pgvector-Routing für inbound aktiv

Ablauf:
1. Event via Webhook empfangen
2. Embedding: title + description + (stack trace summary wenn Sentry)
3. pgvector: Cosine-Similarity vs. alle aktiven Epic-Embeddings
4. >= 0.85 → auto-assign, state = incoming
5. < 0.85 → [UNROUTED] in Triage Station
```

---

## Acceptance Criteria

- [ ] Outbox-Consumer verarbeitet `sync_outbox` zuverlässig (`direction='outbound'`, `state='pending'`)
- [ ] Retry nach Fehler mit korrektem Backoff-Timing
- [ ] Nach 5 Fehlversuchen → `sync_dead_letter`
- [ ] YouTrack Status-Update kommt in Hivemind an
- [ ] Sentry Bug-Report wird in `node_bug_reports` aggregiert
- [ ] Bug-Heatmap im Nexus Grid zeigt Farb-Intensität nach Bug-Count
- [ ] `[DEAD LETTER]`-Items in Triage Station mit Requeue-Option
- [ ] `hivemind/requeue_dead_letter` setzt DLQ-Eintrag deterministisch zurück in `sync_outbox` (`state='pending'`, `attempts=0`)
- [ ] pgvector-Routing: >= 85% Precision nach 2 Wochen Betrieb (KPI)
- [ ] Audit-Retention-Cron bereinigt Payloads korrekt
- [ ] Performance-Budget fuer Nexus Grid und Triage ist dokumentiert und eingehalten

---

## Abhängigkeiten

- Phase 6 abgeschlossen (Eskalation, Notifications)
- Ollama läuft (Phase 3+)

## Öffnet folgende Phase

→ [Phase 8: Volle Autonomie](./phase-8.md)
