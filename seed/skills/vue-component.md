---
title: "Vue 3 Component erstellen"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "reka-ui"]
version_range: { "vue": ">=3.4", "typescript": ">=5.0" }
confidence: 0.85
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
- **Design Tokens** via CSS Custom Properties — **keine hardcoded Farben, Spacing, Radii oder Font-Sizes**
- 4-Schichten-Modell:
  - Layer 0: Design Tokens (`frontend/src/design/tokens.css`, `semantic.css`, `components.css`)
  - Layer 1: Reka UI Primitives (headless)
  - Layer 2: Shared UI Components (`HmButton`, `HmBadge`, `HmInput`, `HmFormGroup` in `components/ui/`)
  - Layer 3: Domain Components (`HmStateBadge`, `HmSourceBadge` in `components/domain/`)
  - Layer 4: Composed Views (`CommandDeck`, `PromptStation`)
- Prefix: `Hm` für alle Shared und Domain Components (Hivemind)
- Props mit TypeScript Interface typisieren
- Emits mit `defineEmits<{...}>()` typisieren
- Prop-Defaults explizit mit `withDefaults()`
- **Immer prüfen:** existiert ein `Hm*`-Component für dieses Pattern? → wiederverwenden, nicht neu stylen

### Dateistruktur

```
frontend/src/
  design/
    tokens.css           ← Primitiven (Farben, Spacing, Radii, Shadows, Fonts)
    semantic.css         ← Semantische Farben (--color-bg, --color-surface, etc.)
    components.css       ← Component-Tokens (--button-*, --badge-*, --card-*, --input-*)
    themes/              ← space-neon.css, industrial-amber.css, operator-mono.css
  components/
    ui/                  ← Generische Bausteine (HmButton, HmBadge, HmInput, ...)
    domain/              ← Business-Context-aware (HmStateBadge, HmSourceBadge, ...)
  views/                 ← Composed Views
  composables/           ← Shared Logic (useAutoMode, useTheme, useToast, ...)
```

### Beispiel

```vue
<script setup lang="ts">
import { HmBadge } from '@/components/ui'

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
  <article class="hm-task-card" :data-state="props.state" @click="emit('click')">
    <h3 class="hm-task-card__title">{{ props.title }}</h3>
    <HmBadge :variant="stateVariant" size="sm">{{ props.state }}</HmBadge>
  </article>
</template>

<style scoped>
.hm-task-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-4);
}

.hm-task-card__title {
  font-size: var(--font-size-sm);
  color: var(--color-text);
}
</style>
```

### Design Token Referenz (aktuell)

| Kategorie | Tokens | Datei |
| --- | --- | --- |
| Semantische Farben | `--color-bg`, `--color-surface`, `--color-surface-alt`, `--color-border`, `--color-text`, `--color-text-muted`, `--color-accent`, `--color-accent-2`, `--color-success`, `--color-warning`, `--color-danger` | `semantic.css` |
| Spacing | `--space-1` (4px) bis `--space-16` (64px) | `tokens.css` |
| Font Sizes | `--font-size-xs` bis `--font-size-4xl` | `tokens.css` |
| Radii | `--radius-sm` (4px), `--radius-md` (8px), `--radius-lg` (12px), `--radius-full` | `tokens.css` |
| Shadows | `--shadow-sm`, `--shadow-md` | `tokens.css` |
| Fonts | `--font-heading`, `--font-body`, `--font-mono` | `tokens.css` |
| Z-Index | `--z-tooltip` (100), `--z-modal` (200), `--z-overlay` (300) | `tokens.css` |
| Button-Tokens | `--button-primary-bg`, `--button-primary-text`, `--button-primary-hover-bg`, `--button-danger-bg`, `--button-secondary-*`, `--button-ghost-*`, `--button-radius`, `--button-sm-*`, `--button-md-*`, `--button-lg-*` | `components.css` |
| Badge-Tokens | `--badge-padding-x`, `--badge-radius`, `--badge-font-size`, `--badge-success-*`, `--badge-warning-*`, `--badge-danger-*`, `--badge-info-*`, `--badge-neutral-*` | `components.css` |
| Card-Tokens | `--card-bg`, `--card-border`, `--card-radius` | `components.css` |
| Input-Tokens | `--input-bg`, `--input-border`, `--input-focus-border`, `--input-radius`, `--input-padding`, `--input-font-size`, `--input-error-border` | `components.css` |

### ⚠ Häufige Fehler

**Hardcoded Werte:** NIEMALS `border-radius: 4px`, `padding: 8px 16px`, `background: #1a2b3c` o.ä. → IMMER `var(--radius-sm)`, `var(--space-2) var(--space-4)`, `var(--color-surface)`.

**Eigene Button-Styles:** NIEMALS `.btn-primary { ... }` im Scoped CSS definieren → IMMER `<HmButton variant="primary">` verwenden.

**Eigene Badge-Styles:** NIEMALS `.badge-success { ... }` → IMMER `<HmBadge variant="success">` verwenden.

### API-Aufrufe — häufige Fehler

**MCP-Tool-Calls:** `POST /api/mcp/call` gibt `{ result: [...] }` zurück (Wrapper-Objekt). Das Array muss mit `.result` extrahiert werden:

```typescript
// FALSCH — result ist ein Objekt, kein Array
const result = await api.callMcpTool('hivemind-get_prompt', { type: 'architekt', epic_id: epicKey })
result.map(r => r.text) // ❌ result.map is not a function

// RICHTIG — api.callMcpTool unwrappt .result intern
// → gibt McpToolResponse[] zurück
```

**Identifier:** Alle Entitäten werden in MCP-Tools per **Key** referenziert (z.B. `epic.epic_key`, `task.task_key`, `skill.skill_key`), **nicht** per UUID. Beispiel:

```typescript
// FALSCH
await api.getPrompt('architekt', undefined, epic.id)        // UUID → 404

// RICHTIG
await api.getPrompt('architekt', undefined, epic.epic_key)  // "EPIC-12" → ✅
```
