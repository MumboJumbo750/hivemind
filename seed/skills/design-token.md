---
title: "Design Token anlegen"
service_scope: ["frontend"]
stack: ["css", "vue3"]
version_range: {}
confidence: 0.5
source_epics: ["EPIC-PHASE-1B"]
guards: []
---

## Skill: Design Token anlegen

### Rolle
Du erstellst oder erweiterst Design Tokens für das Hivemind-UI Design System.

### Konventionen
- Tokens als CSS Custom Properties in Theme-Dateien
- Theme-Dateien in `frontend/src/styles/themes/`
- 3 Pflicht-Themes: `space-neon` (Default), `industrial-amber`, `operator-mono`
- Token-Naming: `--{category}-{variant}` z.B. `--surface-primary`, `--text-muted`
- Keine hardcoded Farben in Components — immer Token-Referenz
- Accessibility: `prefers-reduced-motion` respektieren, sichtbarer Focus-Ring

### Token-Kategorien

| Kategorie | Prefix | Beispiele |
| --- | --- | --- |
| Oberflächen | `--surface-` | `--surface-primary`, `--surface-elevated`, `--surface-sunken` |
| Text | `--text-` | `--text-primary`, `--text-muted`, `--text-accent` |
| Akzente | `--accent-` | `--accent-primary`, `--accent-success`, `--accent-danger` |
| Borders | `--border-` | `--border-subtle`, `--border-strong` |
| Spacing | `--space-` | `--space-xs` (4px) bis `--space-2xl` (48px) |
| Radii | `--radius-` | `--radius-sm`, `--radius-md`, `--radius-lg` |
| Fonts | `--font-` | `--font-mono`, `--font-sans` |
| Fokus | `--focus-` | `--focus-ring-color`, `--focus-ring-width` |

### Beispiel (space-neon Theme)

```css
[data-theme="space-neon"] {
  /* Surfaces */
  --surface-primary: #0a0e1a;
  --surface-elevated: #111827;
  --surface-sunken: #060810;

  /* Text */
  --text-primary: #e2e8f0;
  --text-muted: #64748b;
  --text-accent: #22d3ee;

  /* Accents */
  --accent-primary: #22d3ee;
  --accent-success: #10b981;
  --accent-danger: #ef4444;
  --accent-warning: #f59e0b;

  /* Focus */
  --focus-ring-color: #22d3ee;
  --focus-ring-width: 2px;
}
```

### Theme-Switch

```typescript
// Theme als data-Attribut auf <html> setzen
document.documentElement.setAttribute('data-theme', themeName)
```
