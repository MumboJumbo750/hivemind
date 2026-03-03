---
title: "Design Token anlegen"
service_scope: ["frontend"]
stack: ["css", "vue3"]
version_range: {}
confidence: 0.85
source_epics: ["EPIC-PHASE-1B"]
guards: []
---

## Skill: Design Token anlegen

### Rolle
Du erstellst oder erweiterst Design Tokens für das Hivemind-UI Design System.

### Architektur — 3-Schichten-Modell

Das Token-System besteht aus drei Dateien, die aufeinander aufbauen:

```
frontend/src/design/
  tokens.css        ← Layer 0: Primitiven (Farb-Paletten, Spacing, Radii, Fonts, Shadows)
  semantic.css      ← Layer 1: Semantische Farben (referenzieren Primitiven)
  components.css    ← Layer 2: Component-Tokens (referenzieren Semantische)
  themes/
    space-neon.css          ← Default-Theme (überschreibt Semantische)
    industrial-amber.css
    operator-mono.css
```

### Layer 0 — Primitiven (`tokens.css`)

Farbpaletten, Spacing, Typografie, Radii, Shadows. Werden **nie direkt** in Components verwendet.

```css
:root {
  --primitive-blue-500: #3b82f6;
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;  --space-4: 16px;
  --space-6: 24px; --space-8: 32px; --space-12: 48px; --space-16: 64px;
  --font-size-xs: 0.75rem; --font-size-sm: 0.875rem; --font-size-base: 1rem;
  --radius-sm: 4px; --radius-md: 8px; --radius-lg: 12px; --radius-full: 9999px;
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.5), 0 1px 2px rgba(0,0,0,0.4);
  --shadow-md: 0 4px 6px rgba(0,0,0,0.6), 0 2px 4px rgba(0,0,0,0.5);
  --font-heading: 'Space Grotesk', sans-serif;
  --font-body: 'Inter', sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}
```

### Layer 1 — Semantische Farben (`semantic.css`)

Die **einzigen** Farb-Tokens, die in Components verwendet werden dürfen:

```css
:root {
  --color-bg: #070b14;
  --color-surface: #101a2b;
  --color-surface-alt: #162238;
  --color-border: #223a63;
  --color-text: #e6f0ff;
  --color-text-muted: #7f92b3;
  --color-accent: #20e3ff;
  --color-accent-2: #ff3fd2;
  --color-success: #3cff9a;
  --color-warning: #ffb020;
  --color-danger: #ff4d6d;
}
```

### Layer 2 — Component-Tokens (`components.css`)

Für wiederverwendbare UI-Bausteine (Button, Badge, Card, Input, Modal):

```css
:root {
  /* Button */
  --button-primary-bg: var(--color-accent);
  --button-primary-text: var(--color-bg);
  --button-danger-bg: var(--color-danger);
  --button-radius: var(--radius-sm);

  /* Badge */
  --badge-padding-x: var(--space-2);
  --badge-radius: var(--radius-sm);
  --badge-font-size: var(--font-size-xs);
  --badge-success-bg: rgba(60, 255, 154, 0.15);
  --badge-success-text: var(--color-success);

  /* Card */
  --card-bg: var(--color-surface);
  --card-border: 1px solid var(--color-border);
  --card-radius: var(--radius-md);

  /* Input */
  --input-bg: var(--color-surface-alt);
  --input-border: var(--color-border);
  --input-focus-border: var(--color-accent);
  --input-radius: var(--radius-sm);
  --input-padding: var(--space-2) var(--space-3);
}
```

### Konventionen (Regeln)

1. **Neue Farbe hinzufügen?** → Primitiv in `tokens.css`, Semantik in `semantic.css`, nie direkt Hex in Components
2. **Neues Component?** → Component-Token in `components.css`, dann in der `.vue`-Datei referenzieren
3. **Kein Hardcoding:** Components dürfen nie `#1a2b3c`, `4px`, `8px 16px` schreiben — immer `var(--*)`
4. **Theme-Kompatibilität:** Jeder neue semantische Token muss in allen 3 Themes definiert werden
5. **Accessibility:** `prefers-reduced-motion` respektieren (bereits in `tokens.css` implementiert), sichtbarer Focus-Ring

### Theme-Switch

Themes werden via CSS-Datei-Import gewechselt (kein `data-theme`-Attribut):

```typescript
// composables/useTheme.ts
import { ref, watchEffect } from 'vue'
const theme = ref<'space-neon' | 'industrial-amber' | 'operator-mono'>('space-neon')
// Theme-Dateien überschreiben die semantic.css Werte
```

### ⚠ Veraltete Token-Namen (nicht verwenden!)

| Alt (falsch) | Neu (richtig) |
| --- | --- |
| `--surface-primary` | `--color-surface` |
| `--surface-elevated` | `--color-surface-alt` |
| `--text-primary` | `--color-text` |
| `--text-muted` | `--color-text-muted` |
| `--accent-primary` | `--color-accent` |
| `--accent-success` | `--color-success` |
| `--border-subtle` | `--color-border` |
| `--space-xs`/`--space-md`/`--space-2xl` | `--space-1`/`--space-4`/`--space-12` (numerisch) |
