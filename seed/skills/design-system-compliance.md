---
title: "Design System Compliance — Audit und Enforcement"
service_scope: ["frontend"]
stack: ["css", "typescript", "vue3"]
version_range: { "vue": ">=3.4" }
confidence: 0.8
source_epics: ["EPIC-PHASE-1B"]
guards:
  - title: "TypeScript Check"
    command: "vue-tsc --noEmit"
  - title: "Build Check"
    command: "cd frontend && npm run build"
---

## Skill: Design System Compliance

### Rolle
Du prüfst und korrigierst Vue Components auf Einhaltung des Hivemind Design Systems. Dieser Skill wird beim Refactoring bestehender Components und beim Review neuer Components angewendet.

### Verbotene Patterns (Hardcodes)

Diese Patterns dürfen **nie** in `<style scoped>` auftauchen:

| Verboten | Erlaubt | Warum |
| --- | --- | --- |
| `#1a2b3c`, `#fff`, `rgba(0,0,0,0.5)` | `var(--color-surface)`, `var(--color-text)` | Theme-Kompatibilität |
| `2px`, `4px`, `8px`, `16px` bei `padding`/`margin`/`gap` | `var(--space-1)`, `var(--space-2)`, `var(--space-4)` | Konsistente Abstände |
| `3px`, `4px`, `8px` bei `border-radius` | `var(--radius-sm)`, `var(--radius-md)` | Konsistente Radii |
| `0.75rem`, `14px` bei `font-size` | `var(--font-size-xs)`, `var(--font-size-sm)` | Typo-Skala |
| `.btn-primary { ... }` im Scoped CSS | `<HmButton variant="primary">` | Component-Reuse |
| `.badge-success { ... }` im Scoped CSS | `<HmBadge variant="success">` | Component-Reuse |
| `font-family: 'Inter'` | `var(--font-body)` | Font-Token |

### Erlaubte Ausnahmen

Hardcoded Werte sind **nur** erlaubt für:
- `1px` bei Borders (z.B. `border: 1px solid var(--color-border)`) — kein Token nötig
- `0` für Reset-Werte (`margin: 0`, `padding: 0`)
- `100%`, `auto`, `fit-content` — Layout-Werte
- `min-width`, `max-width` für Layout-Constraints (z.B. `min-width: 160px` bei Dropdowns)
- `transform`, `translate`, `rotate` — Animation-Werte
- SVG-Attribute (`viewBox`, `d`, `cx`, etc.)

### Audit-Checkliste

Für jedes Vue Component (.vue-Datei) prüfen:

#### 1. Token-Compliance
- [ ] Keine Hex-Farben (`#xxx`) im `<style>`-Block
- [ ] Keine `rgba()` mit hardcoded Werten (außer in `components.css` Token-Definitionen)
- [ ] Kein hardcoded `padding`/`margin`/`gap` in Pixel
- [ ] Kein hardcoded `border-radius` in Pixel
- [ ] Kein hardcoded `font-size` in px oder rem

#### 2. Component-Reuse
- [ ] Kein `.btn-*` oder `button`-Styling im Scoped CSS → `<HmButton>` nutzen
- [ ] Kein Badge/Pill-Styling im Scoped CSS → `<HmBadge>` nutzen
- [ ] Kein Input-Styling im Scoped CSS → `<HmInput>` nutzen
- [ ] Kein Label+Input-Wrapper → `<HmFormGroup>` nutzen

#### 3. TypeScript-Qualität
- [ ] Props via `interface Props { ... }` typisiert
- [ ] `defineEmits<{...}>()` mit Event-Typen
- [ ] `withDefaults()` für optionale Props mit Defaults
- [ ] Keine `any`-Types

#### 4. Struktur
- [ ] `<script setup lang="ts">` (keine Options API)
- [ ] Scoped Styles (`<style scoped>`)
- [ ] BEM-ähnliches Naming für CSS-Klassen (`.hm-component__element`)
- [ ] Barrel Export in `index.ts` (für `components/ui/`)

### Quantitative Metriken

Beim Audit eines Views diese Zahlen messen:

```bash
# Hardcoded Farben (Hex + rgba)
grep -c '#[0-9a-fA-F]\{3,6\}\|rgba(' ViewName.vue

# Hardcoded Pixel-Spacing
grep -cP 'padding:.*\d+px|margin:.*\d+px|gap:.*\d+px' ViewName.vue

# Hardcoded Border-Radius
grep -c 'border-radius:.*[0-9]px' ViewName.vue

# Eigene Button-Klassen
grep -c '\.btn' ViewName.vue

# Token-Referenzen (Soll: > 90% aller Style-Werte)
grep -c 'var(--' ViewName.vue
```

**Ziel nach Refactoring:**
- 0 Hardcoded Farben
- 0 Hardcoded Spacing/Radii
- 0 Eigene Button/Badge-Klassen
- \>90% aller Werte sind `var(--*)`-Referenzen

### Reihenfolge bei Migration

1. **Imports hinzufügen:** `import { HmButton, HmBadge } from '@/components/ui'`
2. **Template ersetzen:** `<button class="btn-primary">` → `<HmButton variant="primary">`
3. **Scoped CSS aufräumen:** Gelöschte Klassen entfernen
4. **Verbleibende Hardcodes:** `padding: 8px` → `padding: var(--space-2)`, etc.
5. **Prüfen:** Keine Hex-Farben, keine px-Spacing mehr im `<style>`-Block

### Beispiel-Migration

```vue
<!-- VORHER -->
<template>
  <div class="action-bar">
    <button class="btn-primary" @click="save">Speichern</button>
    <button class="btn-danger btn-sm" @click="remove">Löschen</button>
    <span class="status-badge" :class="'badge-' + status">{{ status }}</span>
  </div>
</template>

<style scoped>
.action-bar { display: flex; gap: 8px; padding: 12px; }
.btn-primary { background: #20e3ff; color: #070b14; padding: 8px 16px; border-radius: 4px; }
.btn-danger { background: #ff4d6d; color: white; }
.btn-sm { padding: 4px 8px; font-size: 0.75rem; }
.status-badge { padding: 2px 8px; border-radius: 3px; font-size: 0.65rem; text-transform: uppercase; }
.badge-active { background: rgba(60, 255, 154, 0.2); color: #3cff9a; }
.badge-pending { background: rgba(255, 176, 32, 0.2); color: #ffb020; }
</style>

<!-- NACHHER -->
<template>
  <div class="action-bar">
    <HmButton variant="primary" @click="save">Speichern</HmButton>
    <HmButton variant="danger" size="sm" @click="remove">Löschen</HmButton>
    <HmBadge :variant="badgeVariant">{{ status }}</HmBadge>
  </div>
</template>

<style scoped>
.action-bar {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3);
}
</style>
```

**Ergebnis:** 12 Zeilen CSS → 4 Zeilen. Null Hardcodes. Components wiederverwendbar.
