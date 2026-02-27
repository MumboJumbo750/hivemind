---
epic_ref: "EPIC-PHASE-1B"
title: "Phase 1b — UI-Konzept"
---

# Phase 1b — UI-Konzept

## Überblick

Phase 1b liefert das erste nutzbare Frontend: Design System mit Sci-Fi-Ästhetik, Layout Shell und Prompt Station mit Inline-Review/Scoping.

## Design-Prinzipien

### Sci-Fi Game HUD
Modern, dunkel, gamelike — als wäre man Commander eines Agenten-Schwarms. Drei Themes: `space-neon` (Default, cyan-betont), `industrial-amber` (warm), `operator-mono` (minimalistisch).

### Token-basiertes Design System
Alle visuellen Eigenschaften als CSS Custom Properties. Kein Hardcoding. Theme-Switch ohne JavaScript-Rerender — nur `data-theme`-Attribut auf `<html>` ändern.

### Reka UI (Headless)
Keine vorgefertigten Component-Libraries. Reka UI liefert Accessibility-Primitives (Dialog, Tabs, Popover), wir stylen komplett selbst.

## Layout Shell

```
┌──────────────────────────────────────────────────┐
│                   System Bar                      │
├──────────┬────────────────────────┬──────────────┤
│          │                        │              │
│   Nav    │     Main Canvas        │   Context    │
│  Sidebar │   (Prompt Station)     │    Panel     │
│          │                        │              │
├──────────┴────────────────────────┴──────────────┤
│                   Status Bar                      │
└──────────────────────────────────────────────────┘
```

## Prompt Station (Kerninteraktion)

Die Prompt Station ist das Herzstück:
- Zeigt den nächsten Step im Workflow
- Generiert Prompt mit Kontext (ab Phase 3)
- Inline-Review wenn Task `in_review`
- Inline-Scoping wenn Epic `incoming`
- Token Radar für Budget-Visualisierung (ab Phase 3)

## Relevante Skills
- `vue-component` — Component-Erstellung
- `design-token` — Token-System
