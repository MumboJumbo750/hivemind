# Design Tokens - Schema (verbindlich)

← [UI-Konzept](./concept.md) | [Index](../../masterplan.md)

---

## Ziel

Dieses Dokument definiert den verbindlichen Token-Vertrag fuer das Frontend. Alle Styles in App-Views und Wrapper-Komponenten muessen ueber Tokens laufen.

---

## Regeln

1. Keine Hardcoded-Werte in Feature-Komponenten (`color`, `background`, `border`, `spacing`, `radius`, `shadow`, `font-size`).
2. Komponenten nutzen nur Semantic- oder Component-Tokens.
3. Themes ueberschreiben nur Semantic-Tokens (nicht Core-Tokens), damit Layout und Spacing stabil bleiben.
4. Reka UI Primitives werden nur ueber Wrapper in `src/components/ui/` gestylt.

---

## Verzeichnisvertrag

```text
frontend/src/design/
  tokens.css                 # Core-Tokens (--space-*, --radius-*, --font-*, --shadow-*, --duration-*)
  semantic.css               # Semantic-Tokens (Fallback-Werte, wird von Themes überschrieben)
  components.css             # Component-Tokens (referenzieren nur Semantic-Tokens via var())
  themes/
    space-neon.css           # Standard-Theme (Default) — überschreibt Semantic-Tokens
    industrial-amber.css     # Alternative 1
    operator-mono.css        # Alternative 2
```

**Ladereihenfolge (index.html / main.ts):** `tokens.css` → `semantic.css` → `components.css` → aktives Theme. Das aktive Theme überschreibt Semantic-Tokens; Component-Tokens greifen automatisch die neuen Werte via `var()`.

---

## Token-Layer

| Layer | Prefix | Beispiel | Zweck |
| --- | --- | --- | --- |
| Core | `--space-*`, `--radius-*`, `--font-*` | `--space-4`, `--radius-md` | Primitive Basis |
| Semantic | `--color-*`, `--surface-*`, `--state-*` | `--color-bg`, `--color-accent` | UI-Bedeutung |
| Component | `--button-*`, `--card-*`, `--input-*` | `--button-primary-bg` | Stabiler Component-Look |

---

## Pflichtschema

### Core-Tokens (Minimum)

```css
--space-0 ... --space-10;
--radius-xs, --radius-sm, --radius-md, --radius-lg, --radius-xl;
--font-heading, --font-body, --font-mono;
--font-size-xs, --font-size-sm, --font-size-md, --font-size-lg, --font-size-xl;
--shadow-sm, --shadow-md, --shadow-lg;
--duration-fast, --duration-base, --duration-slow;
```

### Semantic-Tokens (Minimum)

```css
--color-bg;
--color-surface;
--color-surface-alt;
--color-border;
--color-text;
--color-text-muted;
--color-accent;
--color-accent-2;
--color-success;
--color-warning;
--color-danger;
--focus-ring-color;
```

### Component-Tokens (Minimum)

Component-Tokens referenzieren **ausschließlich Semantic-Tokens** via `var()` — keine Hardcoded-Werte. Dadurch werden sie automatisch von jedem Theme übernommen, ohne dass jedes Theme Component-Tokens überschreiben muss.

**Verbindliche Werte (`frontend/src/design/components.css`):**

```css
/* Buttons */
--button-primary-bg:     var(--color-accent);
--button-primary-fg:     var(--color-bg);          /* dunkler BG auf hellem Accent */
--button-primary-border: var(--color-accent);
--button-ghost-bg:       transparent;
--button-ghost-fg:       var(--color-accent);

/* Cards */
--card-bg:               var(--color-surface);
--card-border:           var(--color-border);

/* Inputs */
--input-bg:              var(--color-surface-alt);
--input-border:          var(--color-border);
--input-fg:              var(--color-text);

/* Badges — Alpha-Overlay auf Semantic-Farbe (Theme-unabhängig) */
--badge-info-bg:         color-mix(in srgb, var(--color-accent) 15%, transparent);
--badge-warning-bg:      color-mix(in srgb, var(--color-warning) 15%, transparent);
--badge-danger-bg:       color-mix(in srgb, var(--color-danger) 15%, transparent);
```

> **Designregel:** Themes überschreiben niemals Component-Tokens direkt — nur Semantic-Tokens. Wenn ein Theme einen abweichenden Button-Look braucht, wird ein neues Semantic-Token definiert (z.B. `--color-cta`) und auf Component-Ebene referenziert.

---

## Theme-Vertrag

Theme-Aktivierung erfolgt ueber `data-theme="<theme-name>"` auf Root-Ebene. Jedes Theme muss mindestens alle Semantic-Tokens aus dem Pflichtschema definieren.

```css
/* space-neon (Default) — themes/space-neon.css */
:root[data-theme="space-neon"] {
  --color-bg:           #070b14;
  --color-surface:      #101a2b;
  --color-surface-alt:  #162238;
  --color-border:       #223a63;
  --color-text:         #e6f0ff;
  --color-text-muted:   #7f92b3;
  --color-accent:       #20e3ff;
  --color-accent-2:     #ff3fd2;
  --color-success:      #3cff9a;
  --color-warning:      #ffb020;
  --color-danger:       #ff4d6d;
  --focus-ring-color:   #20e3ff;
}

/* industrial-amber — themes/industrial-amber.css */
:root[data-theme="industrial-amber"] {
  --color-bg:           #0d0a06;
  --color-surface:      #1a1408;
  --color-surface-alt:  #231c0d;
  --color-border:       #4a3a18;
  --color-text:         #f5e8cc;
  --color-text-muted:   #9a7f52;
  --color-accent:       #f59e0b;
  --color-accent-2:     #ef4444;
  --color-success:      #22c55e;
  --color-warning:      #d97706;  /* bewusst dunkler als accent (#f59e0b) für visuelle Unterscheidung */
  --color-danger:       #ef4444;
  --focus-ring-color:   #f59e0b;
}

/* operator-mono — themes/operator-mono.css */
:root[data-theme="operator-mono"] {
  --color-bg:           #0e0e0e;
  --color-surface:      #1a1a1a;
  --color-surface-alt:  #222222;
  --color-border:       #383838;
  --color-text:         #d4d4d4;
  --color-text-muted:   #737373;
  --color-accent:       #e5e5e5;
  --color-accent-2:     #737373;
  --color-success:      #4ade80;
  --color-warning:      #facc15;
  --color-danger:       #f87171;
  --focus-ring-color:   #e5e5e5;
}
```

---

## DoD fuer UI-PRs

- Token-Dateien enthalten alle Pflicht-Tokens.
- Feature-Komponenten enthalten keine Hardcoded Design-Werte.
- Theme-Switch in Settings aktualisiert `data-theme` zur Laufzeit.
- Reka UI Komponenten laufen ueber lokale Wrapper in `src/components/ui/`.
- Focus-Zustand ist auf allen interaktiven Controls sichtbar (via `--focus-ring-color`).
- Motion respektiert `prefers-reduced-motion` (Animationen reduziert oder deaktiviert).
- Kritische Flows sind per Keyboard bedienbar (Dialog, Dropdown, Tabs, primäre Actions).
- Performance-Budget fuer schwere Views dokumentiert (Prompt-Volltext, Nexus Grid, Triage-Listen).

---

## Performance-Budgets

Konkrete Budgets pro View — Überschreitung muss vor Merge dokumentiert und begründet werden.

| View | Metrik | Budget | Mitigation bei Überschreitung |
| --- | --- | --- | --- |
| **Nexus Grid 2D** | Max Nodes ohne Virtualisierung | 500 Nodes | Ab 500: Canvas-Virtualisierung (Viewport-Culling); ab 2000: LOD (Level of Detail) mit reduzierten Kanten |
| **Nexus Grid 3D** | Max Nodes mit stabilen 30 FPS | 1000 Nodes | Instanced Rendering (Three.js), Frustum Culling |
| **Triage Station** | Max Items lazy-loaded | 100 Items | Virtualisierte Liste (`vue-virtual-scroller`); Paginierung ab 100+ |
| **Prompt Station** | Prompt-Volltext-Rendering | < 200ms für 10.000 Token-Prompt | TipTap `editable:false` ohne Extensions die nicht benötigt werden |
| **Token Radar** | Animation FPS | 60 FPS (Progress-Ring) | CSS `will-change: transform`; bei `prefers-reduced-motion`: statische Anzeige |
| **Command Deck** | Max Epics + Tasks (flache Liste) | 200 Items | Paginierung; virtualisierte Liste ab 100+ |
| **Wiki Breadcrumb** | Rekursive Kategorie-Auflösung | < 50ms für 5 Ebenen Tiefe | Rekursive CTE mit `max_depth=10`; Breadcrumbs im API-Response vorberechnet |
| **Notification Tray** | Max sichtbare Notifications | 50 Items | Ältere Einträge hinter [ALLE ANZEIGEN] verstecken |

> **Messmethode:** Lighthouse Performance Score >= 80 für alle Views mit Dummy-Daten (max Budget-Grenze). CI-Pipeline prüft auf Regression bei jeder PR die eine View ändert.

---

## Accessibility-Spezifikation

### WCAG-Konformitätslevel

**Ziel: WCAG 2.1 Level AA** für alle interaktiven Komponenten. Level AAA wird für Text-Kontraste auf kritischen Elementen (SLA-Timer, Guard-Status) angestrebt.

### Contrast Ratios (Minimum)

| Element | Ratio-Anforderung | Prüfung |
| --- | --- | --- |
| `--color-text` auf `--color-bg` | >= 7:1 (AAA) | Alle Themes |
| `--color-text` auf `--color-surface` | >= 4.5:1 (AA) | Alle Themes |
| `--color-text-muted` auf `--color-surface` | >= 4.5:1 (AA) | **Kritisch:** space-neon `#7f92b3` auf `#101a2b` = 4.8:1 ✔, industrial-amber `#9a7f52` auf `#1a1408`: prüfen! |
| `--color-accent` auf `--color-bg` | >= 3:1 (AA für Large Text / UI) | Buttons, Badges, Links |
| `--color-warning` vs. `--color-accent` | Visuell unterscheidbar (nicht identisch) | industrial-amber: warning=#d97706, accent=#f59e0b |
| Focus-Ring | >= 3:1 gegen Hintergrund | `--focus-ring-color` pro Theme geprüft |

### Screen-Reader-Strategie

| Bereich | ARIA-Pattern | Details |
| --- | --- | --- |
| **SSE-Updates** (neue Notifications, State-Changes) | `aria-live="polite"` Region | Unsichtbare Live-Region im Layout; neue Events werden als Text gepusht |
| **SLA-Timer** | `aria-label` mit Zeitangabe + `aria-live="assertive"` bei < 1h | Screenreader ankündigt kritische SLA |
| **State-Badges** | `role="status"` + `aria-label="Task Status: in_review"` | Farbe allein nicht aussagekräftig |
| **Guard-Status** | `role="list"` mit `aria-label` pro Guard | Status + Command + Ergebnis als Label |
| **Nexus Grid** | `role="application"` + Keyboard-Navigation | Nodes per Tab erreichbar; Detail per Enter |
| **Modals** | Reka Dialog mit Focus-Trap | Automatisch via Reka UI |
| **Navigation** | `role="navigation"` + `aria-current="page"` | NavSidebar mit Lock-State als `aria-disabled` |

### Keyboard-Navigation-Map

| Kontext | Tasten | Aktion |
| --- | --- | --- |
| **Global** | `Ctrl+K` | Spotlight-Suche (öffnet HivemindSearch) |
| **Global** | `Ctrl+1–9` | View wechseln (1=Station, 2=Quests, ...) |
| **Global** | `Escape` | Offenes Modal/Overlay schließen |
| **Prompt Station** | `Ctrl+C` (im Prompt-Bereich) | Prompt in Zwischenablage kopieren |
| **Command Deck** | `Enter` auf Epic/Task | Detail öffnen |
| **Command Deck** | `R` auf Task in `in_review` | Review Panel öffnen |
| **Triage** | `Tab` / `Shift+Tab` | Zwischen Cards navigieren |
| **Triage** | `M` auf Card | Merge/Accept |
| **Triage** | `X` auf Card | Reject/Ignore |
| **Nexus Grid** | Pfeiltasten | Viewport verschieben |
| **Nexus Grid** | `+` / `-` | Zoom In / Out |
| **Nexus Grid** | `Enter` auf Node | Node-Detail Panel öffnen |
| **Wiki** | `E` | Editor-Modus (wenn berechtigt) |
| **Settings** | `Tab` zwischen Tabs | Tab wechseln |
| **Modals** | `Tab` / `Shift+Tab` | Focus innerhalb Modal |
| **Modals** | `Enter` | Primäre Aktion bestätigen |

---

## `prefers-reduced-motion` — Implementierungsstrategie

Bei `prefers-reduced-motion: reduce` gelten folgende Regeln:

| Animation | Normales Verhalten | Reduziertes Verhalten |
| --- | --- | --- |
| **State-Transition Pulse** | Pulse-Effekt bei Task-Übergängen | `--duration-fast/base/slow` → `0ms` — kein Pulse, nur Farbwechsel |
| **Fog of War Radial Reveal** | Scan-Welle über Grid-Nodes | Sofortiges Einblenden (opacity 0 → 1, no transition) |
| **Token Radar Progress-Ring** | Animierter Ring | Statischer Ring (nur finaler Wert) |
| **Guard Sequential Reveal** | Sequenzielles Aufblinken | Alle Guards gleichzeitig einblenden |
| **SLA-Timer Farb-Transition** | Smooth Color-Transition (amber → rot) | Instant Color-Switch bei Schwellwert |
| **Discovery Session Pulse** | Pulsierender Badge | Statischer Badge mit Icon |
| **Skill Pinning Snap** | Aufleuchten + physisches Einrasten | Sofortiges Einreihen ohne Animation |

**CSS-Implementation:**

```css
@media (prefers-reduced-motion: reduce) {
  :root {
    --duration-fast: 0ms;
    --duration-base: 0ms;
    --duration-slow: 0ms;
  }
  
  /* Transitions die rein dekorativ sind: komplett deaktivieren */
  .pulse-effect,
  .scan-wave,
  .sequential-reveal {
    animation: none !important;
    transition: none !important;
  }
  
  /* Opacity-Transitions bleiben erlaubt (für Einblend-Effekte) aber instant */
  .fade-in {
    transition-duration: 0ms;
  }
}
```

> **Grundregel:** Alle `--duration-*` Tokens werden auf `0ms` gesetzt. Einzelne Komponenten die zusätzliche `animation`-Properties nutzen, müssen diese explizit deaktivieren. Rein informationale Animationen (z.B. Progress-Räder mit dynamischem Wert) zeigen den Endwert statisch.
