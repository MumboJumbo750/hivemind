---
epic_ref: EPIC-PHASE-7
title: Phase 7 - Technischer Kontext und Vorarbeiten
---

# Phase 7 - Technischer Kontext

## Bestehende Infrastruktur (Phase 1-6)

### Outbox-System (Phase F)
- sync_outbox-Tabelle mit direction, state, attempts, payload
- sync_dead_letter-Tabelle fuer fehlgeschlagene Entries
- Bestehender Consumer: app/services/outbox_consumer.py (nur peer_outbound)
- APScheduler-Job registriert in main.py
- Ed25519-Signing + Hub-Relay-Fallback

### Webhook-Ingest (Phase 3)
- Endpoints: POST /api/webhooks/youtrack, POST /api/webhooks/sentry
- HMAC-SHA256-Signaturvalidierung
- Payload-Normalisierung + Idempotenz
- Schreibt direction=inbound in sync_outbox

### Embedding-Service (Phase 3)
- app/services/embedding_service.py mit OllamaProvider
- Circuit-Breaker mit adaptivem Backoff
- HNSW-Indexes auf skills, wiki_articles, epics

### Triage (Phase 3+6)
- app/services/triage_service.py mit route_event/ignore_event
- SSE-Events: triage_routed, triage_escalated
- SLA-Cron + Backup-Owner-Eskalation

### Nexus Grid (Phase 5)
- Cytoscape.js 2D Graph mit Cola-Layout
- code_nodes + code_edges Tabellen
- Fog-of-War: explored_at-Timestamp

## Phase 7 ergaenzt
1. outbound-Consumer fuer YouTrack/Sentry
2. Exponential Backoff: next_retry_at = now() + 2^attempts * 60s
3. pgvector Auto-Routing: inbound Events -> Epic via Cosine-Similarity
4. Bug-Aggregation: Sentry Stack-Traces -> node_bug_reports
5. DLQ-MCP-Tools: requeue_dead_letter, discard_dead_letter
6. Bug Heatmap: Nexus Grid Layer
7. KPI-Dashboard: 6 Kern-KPIs mit stuendlichem Cache
8. Sync-Status-Panel in Settings
