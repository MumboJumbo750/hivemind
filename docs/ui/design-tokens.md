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
  --color-warning:      #f59e0b;
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
