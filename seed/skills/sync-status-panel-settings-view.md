---
title: Sync-Status-Panel (Settings View)
service_scope:
- frontend
stack:
- typescript
- vue3
confidence: 0.5
source_epics:
- EPIC-PHASE-7
---

## Skill: Sync-Status-Panel (Settings View)

### Rolle
Du implementierst ein Sync-Status-Panel in der Settings View. Es zeigt den Zustand der Outbox-Queue, letzte erfolgreiche Syncs und fehlgeschlagene Syncs.

### Konventionen
- Platzierung: Settings View, eigene Sektion/Tab "Sync Status"
- Daten: `GET /api/sync-outbox?limit=10` + Aggregat-Endpoint für Queue-Größe
- Refresh: Auto-Refresh alle 30s oder manueller Refresh-Button
- Drei Bereiche:
  1. **Queue-Status**: Outbox-Größe pro Direction (outbound, peer_outbound, inbound)
  2. **Letzte Syncs**: Erfolgreiche deliveries (Timestamp, Target, Type)
  3. **Fehlgeschlagen**: Aktuelle Retry-Items + DLQ-Count

### Panel-Struktur

```vue
<template>
  <section class="sync-status-panel">
    <h3>Sync Status</h3>
    
    <!-- Queue-Sizes -->
    <div class="queue-grid">
      <SyncQueueCard label="Outbound" :count="queueSizes.outbound" />
      <SyncQueueCard label="Federation" :count="queueSizes.peer_outbound" />
      <SyncQueueCard label="Inbound" :count="queueSizes.inbound" />
      <SyncQueueCard label="Dead Letters" :count="queueSizes.dead_letter" variant="danger" />
    </div>
    
    <!-- Recent Syncs -->
    <h4>Letzte erfolgreiche Syncs</h4>
    <ul class="sync-list">
      <li v-for="s in recentSyncs" :key="s.id">
        {{ s.entity_type }} → {{ s.target }} ({{ formatTimeAgo(s.completed_at) }})
      </li>
    </ul>
    
    <!-- Failed -->
    <h4>Fehlgeschlagene Syncs</h4>
    <ul class="sync-list sync-list--errors">
      <li v-for="f in failedSyncs" :key="f.id">
        {{ f.entity_type }} — Attempt {{ f.attempts }}/{{ maxAttempts }}
        <span class="error">{{ f.error }}</span>
      </li>
    </ul>
  </section>
</template>
```

### Wichtig
- Queue-Count von 0 = alles synchron → grüner Status-Indikator
- DLQ-Count > 0 → roter Badge + Link zu Triage Station
- Panel ist readonly — Aktionen (Requeue, Discard) nur über Triage Station
