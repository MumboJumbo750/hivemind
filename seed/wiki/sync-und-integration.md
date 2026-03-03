---
slug: sync-und-integration
title: "Sync & Integration — Externe Systeme anbinden"
tags: [sync, outbox, youtrack, sentry, github, dlq, phase-7]
linked_epics: [EPIC-PHASE-7, EPIC-PHASE-8]
---

# Sync & Integration — Externe Systeme anbinden

Hivemind integriert sich bidirektional mit externen Systemen: YouTrack, Sentry, GitHub, GitLab. Das Outbox-Pattern garantiert zuverlässigen async Transport.

## Outbox-Pattern

Alle ausgehenden Sync-Nachrichten werden zuerst in die `sync_outbox`-Tabelle geschrieben (gleiche Transaktion wie die fachliche Änderung). Ein Consumer verarbeitet sie asynchron:

| Direction | Zweck |
| --- | --- |
| `peer_outbound` | Federation: Skill/Wiki/Task an Peers (Phase F) |
| `outbound` | YouTrack/Sentry/GitHub-Sync (Phase 7) |
| `inbound` | Webhook-Events für Triage-Routing |

## Dead Letter Queue (DLQ)

Nach `HIVEMIND_DLQ_MAX_ATTEMPTS` (Default: 5) Fehlversuchen wird ein Outbox-Eintrag in die DLQ verschoben (`state = 'dead_letter'`). MCP-Tools: `requeue_dead_letter`, `discard_dead_letter`.

**Wichtig:** Erfolgreiche outbound-Einträge werden **gelöscht**, nicht auf einen Status gesetzt. Nur `'pending'` und `'dead_letter'` als States.

## pgvector Auto-Routing (Phase 7)

Inbound-Events werden automatisch einem Epic zugeordnet via Cosine-Similarity auf Embeddings. Schwellwert: `HIVEMIND_ROUTING_THRESHOLD` (Default: 0.85). Unter dem Schwellwert → `[UNROUTED]` für manuelle Triage.

## GitHub Projects V2 Sync (Phase 8)

Bidirektional: Task-State-Changes → GitHub Board, Board-Änderungen → `[UNROUTED]`. GitHub-Board-Änderungen erzeugen NIE automatische State-Changes in Hivemind (Review-Gate-Schutz).
