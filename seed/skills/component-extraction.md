---
title: "Component Extraction — Pattern zu wiederverwendbarem Component"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "reka-ui"]
version_range: { "vue": ">=3.4", "typescript": ">=5.0" }
confidence: 0.8
source_epics: ["EPIC-PHASE-1B"]
guards:
  - title: "TypeScript Check"
    command: "vue-tsc --noEmit"
  - title: "Lint"
    command: "eslint src/ --ext .vue,.ts"
---

## Skill: Component Extraction

### Rolle
Du identifizierst wiederkehrende UI-Patterns im Frontend-Code und extrahierst sie in wiederverwendbare Vue 3 Components.

### Wann extrahieren?

**Regel: ≥2 Vorkommen desselben Patterns → Component extrahieren.**

Typische Kandidaten:
- **Buttons** mit gleicher Struktur aber verschiedenen Varianten → `HmButton`
- **Badges/Pills** mit `rgba(color, alpha)` Background + farbiger Text → `HmBadge`
- **Input-Felder** mit Label + Error-State → `HmInput` + `HmFormGroup`
- **Leere-Liste-Fallback** mit Icon + Text → `HmEmptyState`
- **Key-Value-Zeilen** in Detail-Panels → `HmKeyValue`
- **Action-Toolbars** mit Flex-Row Buttons → `HmToolbar`

### Extraction-Prozess

#### 1. Pattern identifizieren
```bash
# Suche nach duplizierten CSS-Klassen
grep -rn "\.btn-primary" frontend/src/ --include="*.vue" | wc -l
grep -rn "border-radius:.*3px\|4px\|8px" frontend/src/ --include="*.vue" | wc -l
```

#### 2. Props ableiten

Aus den Variationen des Patterns die Props-Interface ableiten:

```typescript
// Vorher: 11 Views mit jeweils eigenem .btn-primary, .btn-danger, .btn-sm
// → Props-Interface:
interface Props {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  icon?: string
}
```

#### 3. Slots für Flexibilität

```vue
<template>
  <button class="hm-button" :class="classes" :disabled="disabled || loading">
    <slot name="icon" />
    <slot />  <!-- Default-Slot für Label -->
  </button>
</template>
```

#### 4. Component-Tokens erstellen

Neues Component braucht eigene Tokens in `frontend/src/design/components.css`:

```css
:root {
  --button-primary-bg: var(--color-accent);
  --button-primary-text: var(--color-bg);
  --button-radius: var(--radius-sm);
  --button-sm-padding: var(--space-1) var(--space-2);
  --button-md-padding: var(--space-2) var(--space-4);
}
```

#### 5. Barrel Export

Jedes neue Component in `frontend/src/components/ui/index.ts` exportieren:

```typescript
export { default as HmButton } from './HmButton.vue'
export { default as HmBadge } from './HmBadge.vue'
```

#### 6. Migration — View-für-View

```vue
<!-- VORHER (in jedem View dupliziert) -->
<button class="btn-primary" @click="save">Speichern</button>
<style scoped>
.btn-primary {
  background: var(--color-accent);
  color: var(--color-bg);
  padding: 8px 16px;
  border-radius: 4px;
}
</style>

<!-- NACHHER -->
<HmButton variant="primary" @click="save">Speichern</HmButton>
<!-- Kein scoped CSS nötig! -->
```

### Tier-Modell

| Tier | Wo | Beispiele | Abhängigkeit |
| --- | --- | --- | --- |
| UI Components | `components/ui/` | `HmButton`, `HmBadge`, `HmInput`, `HmFormGroup` | Nur Design Tokens |
| Domain Components | `components/domain/` | `HmStateBadge`, `HmSourceBadge`, `HmPriorityBadge` | Nutzen UI Components intern |
| Views | `views/` | `CommandDeck`, `PromptStation` | Nutzen beide Tiers |

### Checkliste pro Extraction

- [ ] Props-Interface mit TypeScript typisiert
- [ ] Alle Varianten über Props steuerbar (nicht über CSS-Klassen von außen)
- [ ] `withDefaults()` für sinnvolle Defaults
- [ ] `defineEmits<{...}>()` für alle Events
- [ ] **Null** hardcoded Farben, Spacing, Radii → nur `var(--*)`
- [ ] Component-Tokens in `components.css` angelegt
- [ ] Barrel Export in `index.ts`
- [ ] Mindestens 2 Views refactored, die das alte Pattern nutzen
- [ ] Scoped CSS im View reduziert (alte `.btn-*` / `.badge-*` Klassen entfernt)

### ⚠ Anti-Patterns

1. **CSS-Klassen-Props:** Nicht `<HmBadge class="badge-success">` → sondern `<HmBadge variant="success">`
2. **Style-Override von außen:** Nicht `:deep(.hm-button) { padding: 12px }` → sondern `size="lg"` Prop
3. **Zu generisch:** Kein `<HmBox>` das alles kann → spezifische Components mit klarem Zweck
4. **Zu spezifisch:** Kein `<HmTriageBadge>` wenn `<HmBadge variant="info">` reicht
