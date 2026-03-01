---
title: "Vue 3 Component erstellen"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "reka-ui"]
version_range: { "vue": ">=3.4", "typescript": ">=5.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1B"]
guards:
  - title: "TypeScript Check"
    command: "vue-tsc --noEmit"
  - title: "Lint"
    command: "eslint src/ --ext .vue,.ts"
---

## Skill: Vue 3 Component erstellen

### Rolle
Du erstellst eine Vue 3 SFC (Single File Component) für das Hivemind-Frontend.

### Konventionen
- **Composition API** mit `<script setup lang="ts">` — keine Options API
- **Reka UI** für Headless-Primitives (Dialog, Popover, Tabs, etc.)
- **Design Tokens** via CSS Custom Properties — keine hardcoded Farben/Spacing
- 4-Schichten-Modell:
  - Layer 0: Design Tokens (CSS Variables)
  - Layer 1: Reka UI Primitives
  - Layer 2: Domain Components (`HvTaskCard`, `HvEpicBadge`)
  - Layer 3: Composed Views (`CommandDeck`, `PromptStation`)
- Prefix: `Hv` für alle Domain Components
- Props mit TypeScript Interface typisieren
- Emits mit `defineEmits<{...}>()` typisieren

### Beispiel

```vue
<script setup lang="ts">
interface Props {
  title: string
  state: 'incoming' | 'scoped' | 'ready' | 'in_progress'
  priority?: 'low' | 'medium' | 'high' | 'critical'
}

const props = withDefaults(defineProps<Props>(), {
  priority: 'medium'
})

const emit = defineEmits<{
  click: []
}>()
</script>

<template>
  <article class="hv-task-card" :data-state="props.state" @click="emit('click')">
    <h3 class="hv-task-card__title">{{ props.title }}</h3>
    <span class="hv-task-card__badge" :data-priority="props.priority">
      {{ props.state }}
    </span>
  </article>
</template>

<style scoped>
.hv-task-card {
  background: var(--surface-primary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-md);
}
</style>
```

### Design Token Referenz
- Farben: `--surface-*`, `--text-*`, `--accent-*`, `--border-*`
- Spacing: `--space-xs` bis `--space-2xl`
- Radii: `--radius-sm`, `--radius-md`, `--radius-lg`
- Fonts: `--font-mono`, `--font-sans`

### API-Aufrufe — häufige Fehler

**MCP-Tool-Calls:** `POST /api/mcp/call` gibt `{ result: [...] }` zurück (Wrapper-Objekt). Das Array muss mit `.result` extrahiert werden:

```typescript
// FALSCH — result ist ein Objekt, kein Array
const result = await api.callMcpTool('hivemind/get_prompt', { type: 'architekt', epic_id: epicKey })
result.map(r => r.text) // ❌ result.map is not a function

// RICHTIG — api.callMcpTool unwrappt .result intern
// → gibt McpToolResponse[] zurück
```

**Identifier:** Epics und Tasks werden in MCP-Tools per **Key** referenziert (`epic.epic_key`, `task.task_key`), **nicht** per UUID (`epic.id`). Beispiel:

```typescript
// FALSCH
await api.getPrompt('architekt', undefined, epic.id)        // UUID → 404

// RICHTIG
await api.getPrompt('architekt', undefined, epic.epic_key)  // "EPIC-PHASE-4" → ✅
```
