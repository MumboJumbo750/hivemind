---
title: Triage Station DLQ-Kategorie (Frontend)
service_scope:
- frontend
stack:
- typescript
- vue3
confidence: 0.5
source_epics:
- EPIC-PHASE-7
---

## Skill: Triage Station DLQ-Kategorie (Frontend)

### Rolle
Du erweiterst die Triage Station View um eine `[DEAD LETTER]`-Kategorie. Dead Letters sind fehlgeschlagene Outbox-Einträge die nach max_attempts in die DLQ verschoben wurden.

### Konventionen
- Neue Tab/Kategorie in Triage Station: `[DEAD LETTER]`
- Datenstrom: SSE-Event `triage_dlq_updated` triggert Refresh
- API: `GET /api/sync-outbox?state=dead_letter` oder dedizierter DLQ-Endpoint
- Aktionen pro DLQ-Item:
  - "Erneut versuchen" → `POST /api/triage/dead-letters/{id}/requeue` (oder MCP-Tool)
  - "Verwerfen" → `POST /api/triage/dead-letters/{id}/discard`
- Detail-Ansicht: Fehler-Nachricht, Payload, Timestamps, Attempt-History

### DLQ-Liste

```vue
<template>
  <div class="dlq-list">
    <div v-for="item in deadLetters" :key="item.id" class="dlq-item">
      <div class="dlq-header">
        <span class="badge badge-danger">DLQ</span>
        <span class="entity-type">{{ item.entity_type }}</span>
        <span class="system">{{ item.system }}</span>
        <time>{{ formatDate(item.created_at) }}</time>
      </div>
      <div class="dlq-error">{{ item.error }}</div>
      <div class="dlq-actions">
        <HivemindButton variant="secondary" @click="requeue(item.id)">
          Erneut versuchen
        </HivemindButton>
        <HivemindButton variant="ghost" @click="discard(item.id)">
          Verwerfen
        </HivemindButton>
      </div>
    </div>
  </div>
</template>
```

### Wichtig
- DLQ-Count wird als Badge auf dem Triage-Tab angezeigt (Attention-Indikator)
- Requeue setzt den Dead Letter zurück in sync_outbox mit attempts=0
- Discard ist ein Soft-Delete (bleibt in DB für Audit)
- Error-Details sind expandable (Klick zeigt Full Payload + Stack Trace)
