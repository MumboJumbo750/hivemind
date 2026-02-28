# Worker-Prompts — EPIC-PHASE-1B

Jeden Prompt einzeln in deinen AI-Client einfügen. Reihenfolge einhalten (Abhängigkeiten).
Kein MCP-Backend in Phase 1b — der Worker implementiert direkt im Workspace.

---

## TASK-1B-001 — Vue 3 + Vite + TypeScript + Reka UI Scaffold

```
## Rolle: Worker

Du arbeitest an TASK-1B-001 im Rahmen von EPIC-PHASE-1B (Phase 1b — Design & Prompt Station).

### Dein Auftrag

Fehlende npm-Abhängigkeiten im bestehenden Frontend-Scaffold installieren und konfigurieren.

Das Frontend liegt in `frontend/`. Der aktuelle Stand in `frontend/package.json`:
- Vorhanden: `vue ^3.5`, `vue-router ^4.5`, `pinia ^2.3`, `vite ^6.1`, `vue-tsc`
- Noch NICHT installiert: `@reka-ui/core`, `@fontsource/space-grotesk`, `@fontsource/inter`, `@fontsource/jetbrains-mono`

Folgendes ist zu tun:

1. Installiere die fehlenden Pakete via npm im `frontend/`-Verzeichnis:
   - `@reka-ui/core` (als dependency)
   - `@fontsource/space-grotesk`, `@fontsource/inter`, `@fontsource/jetbrains-mono` (als dependencies)

2. Passe `frontend/src/main.ts` an:
   - Importiere alle drei @fontsource-Pakete (nur den Default-Import, z.B. `import '@fontsource/inter'`)
   - Bootstrap: `createApp(App).use(router).use(createPinia()).mount('#app')`
   - Importiere `createRouter`/`createWebHistory` aus `vue-router` und registriere einen minimalen Router (vorerst leer oder mit einer Catch-All-Route)
   - Importiere `createPinia` aus `pinia`

3. Passe `frontend/src/App.vue` an:
   - Minimaler Einstiegspunkt: enthält nur `<RouterView />` im Template
   - Kein Domain-Inhalt, kein Styling außer `height: 100vh` auf root

### Definition of Done

- [ ] `npm install` läuft ohne Fehler durch
- [ ] `@reka-ui/core` ist in package.json als dependency gelistet und importierbar
- [ ] Alle drei @fontsource-Pakete sind installiert und in `main.ts` importiert
- [ ] `createApp(App).use(router).use(pinia).mount('#app')` funktioniert in `main.ts`
- [ ] `vite dev` startet ohne Fehler, Browser zeigt leere Seite ohne Konsolenfehler
- [ ] TypeScript-Compilation (`tsc --noEmit`) gibt keine Fehler aus

### Einschränkungen

- Nur im Verzeichnis `frontend/` arbeiten (außer package.json-Updates)
- Kein Inhalt, keine Domain-Logik — reines Scaffold/Bootstrap
- Noch keine CSS-Dateien anlegen (kommt in TASK-1B-003)
- Noch keine vollständigen Routes definieren (kommt in TASK-1B-008)
```

---

## TASK-1B-002 — @hey-api/openapi-ts Setup + Backend OpenAPI-Export

```
## Rolle: Worker

Du arbeitest an TASK-1B-002 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-001 ist abgeschlossen (`@reka-ui/core` etc. bereits installiert).

### Dein Auftrag

Zwei zusammengehörige Setup-Aufgaben (Frontend-Codegen-Config + Backend-Export-Script).

**Teil 1 — Frontend:**

1. Installiere `@hey-api/openapi-ts` und `@hey-api/client-fetch` als devDependencies im `frontend/`-Verzeichnis.

2. Erstelle `frontend/openapi-ts.config.ts`:
   ```ts
   import { defineConfig } from '@hey-api/openapi-ts'
   export default defineConfig({
     input: '../openapi.json',
     output: 'src/api/client/',
     client: '@hey-api/client-fetch',
   })
   ```

3. Füge in `frontend/package.json` unter `scripts` hinzu:
   `"generate:api": "openapi-ts"`

4. Erstelle den Ordner `frontend/src/api/client/` mit einer leeren `.gitkeep`-Datei.

5. Füge zu `frontend/.gitignore` (neu anlegen falls nicht vorhanden) hinzu:
   ```
   src/api/client/*.ts
   !src/api/client/.gitkeep
   ```

**Teil 2 — Backend:**

6. Erstelle `backend/scripts/export_openapi.py`:
   ```python
   #!/usr/bin/env python3
   """Exportiert das FastAPI OpenAPI-Schema statisch als openapi.json in den Repo-Root."""
   import json
   import sys
   from pathlib import Path

   # Repo-Root relativ zu diesem Script ermitteln
   REPO_ROOT = Path(__file__).parent.parent.parent

   # Backend-Paket importierbar machen
   sys.path.insert(0, str(Path(__file__).parent.parent))

   from app.main import app

   schema = app.openapi()
   output_path = REPO_ROOT / "openapi.json"
   output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False))
   print(f"OpenAPI schema written to {output_path}")
   ```
   Das Script muss ausführbar sein via `python scripts/export_openapi.py` aus dem `backend/`-Verzeichnis.

### Definition of Done

- [ ] `frontend/openapi-ts.config.ts` existiert mit korrekten input/output/client-Feldern
- [ ] `npm run generate:api` im frontend/-Verzeichnis läuft ohne Fehler (setzt eine gültige openapi.json voraus)
- [ ] `frontend/src/api/client/` Ordner existiert mit `.gitkeep`
- [ ] Generierte Dateien sind im .gitignore eingetragen
- [ ] `backend/scripts/export_openapi.py` existiert und schreibt bei Ausführung eine valide `openapi.json` in den Repo-Root
- [ ] Das generierte `openapi.json` enthält alle Phase-1b-relevanten Endpoints (projects, epics, tasks)

### Einschränkungen

- Keine Änderungen an Backend-Routen oder -Modellen — nur das Export-Script
- Das Script soll idempotent sein (mehrfaches Ausführen überschreibt die Datei problemlos)
```

---

## TASK-1B-003 — CSS Design System Layer 1 — Core, Semantic, Component Tokens

```
## Rolle: Worker

Du arbeitest an TASK-1B-003 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-001 abgeschlossen.

### Dein Auftrag

Reines CSS-Token-System in `frontend/src/design/` anlegen. Kein Vue-Code — ausschließlich CSS Custom Properties. Drei Dateien:

**1. `frontend/src/design/tokens.css` — Core-Tokens (Primitive Basiswerte):**

`:root` Block mit:
- Farb-Primitiven (neutral benannt): `--primitive-blue-50` bis `--primitive-blue-900`, analog für gray, green, yellow, red, pink
- Spacing-Skala: `--space-1: 4px`, `--space-2: 8px`, `--space-3: 12px`, `--space-4: 16px`, `--space-6: 24px`, `--space-8: 32px`, `--space-12: 48px`, `--space-16: 64px`
- Font-Size-Skala: `--font-size-xs: 0.75rem`, `--font-size-sm: 0.875rem`, `--font-size-base: 1rem`, `--font-size-lg: 1.125rem`, `--font-size-xl: 1.25rem`, `--font-size-2xl: 1.5rem`, `--font-size-3xl: 1.875rem`, `--font-size-4xl: 2.25rem`
- Border-Radius: `--radius-sm: 4px`, `--radius-md: 8px`, `--radius-lg: 12px`, `--radius-full: 9999px`
- Schatten: `--shadow-sm`, `--shadow-md` (passend zu einem dunklen Theme)
- Z-Index: `--z-tooltip: 100`, `--z-modal: 200`, `--z-overlay: 300`
- Transition: `--transition-duration: 200ms`, `--animation-duration: 300ms`
- Font-Families: `--font-heading: 'Space Grotesk', sans-serif`, `--font-body: 'Inter', sans-serif`, `--font-mono: 'JetBrains Mono', monospace`

**2. `frontend/src/design/semantic.css` — Semantic-Tokens (Fallback-Werte, überschrieben durch Themes):**

`:root` Block mit Fallback-Werten (dunkles Default):
```css
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
```

**3. `frontend/src/design/components.css` — Component-Tokens:**

`:root` Block mit Component-spezifischen Tokens (referenzieren Semantic-Tokens via `var()`):
```css
/* Button */
--button-primary-bg: var(--color-accent);
--button-primary-text: var(--color-bg);
--button-primary-hover-bg: /* leicht heller als accent */;
--button-danger-bg: var(--color-danger);

/* Card */
--card-bg: var(--color-surface);
--card-border: 1px solid var(--color-border);
--card-radius: var(--radius-md);

/* Input */
--input-bg: var(--color-surface-alt);
--input-border: var(--color-border);
--input-focus-border: var(--color-accent);

/* Modal */
--modal-bg: var(--color-surface);
--modal-backdrop: rgba(0, 0, 0, 0.7);

/* Sidebar */
--sidebar-bg: var(--color-surface);
--sidebar-width: 240px;
--sidebar-collapsed-width: 48px;

/* Status Bar */
--statusbar-bg: var(--color-surface-alt);
--statusbar-height: 24px;

/* System Bar */
--systembar-bg: var(--color-surface);
--systembar-height: 32px;
```

**4. Alle drei Dateien in `frontend/src/main.ts` importieren:**
```ts
import './design/tokens.css'
import './design/semantic.css'
import './design/components.css'
```

### Definition of Done

- [ ] `src/design/tokens.css` existiert mit vollständiger Core-Token-Skala
- [ ] `src/design/semantic.css` existiert mit allen semantischen Farb-Tokens als Fallback-Werte
- [ ] `src/design/components.css` existiert mit allen Component-Tokens für Button, Card, Input, Modal, Sidebar
- [ ] Alle drei Dateien werden in `main.ts` importiert
- [ ] Browser-DevTools zeigen die Custom Properties auf `:root` an
- [ ] Kein Vue-Code in den CSS-Dateien — nur Custom Properties

### Einschränkungen

- Keine Vue-Dateien erstellen — nur CSS
- Keine Theme-spezifischen Werte in `tokens.css` oder `components.css` hardcoden — immer via `var()` referenzieren
- Theme-Dateien kommen in TASK-1B-004
```

---

## TASK-1B-004 — Theme Engine — 3 Themes + useTheme Composable

```
## Rolle: Worker

Du arbeitest an TASK-1B-004 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-003 abgeschlossen (Design-Token-Layer existiert).

### Dein Auftrag

Theme-System über `data-theme`-Attribut auf `<html>` implementieren.

**1. `frontend/src/design/themes/space-neon.css` (Default-Theme):**

Selektor: `:root, [data-theme="space-neon"]`

Exakte Referenzwerte (keine Abweichung):
```css
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
```
Font-Variablen: `--font-heading`, `--font-body`, `--font-mono` auf die @fontsource-Familien setzen.

**2. `frontend/src/design/themes/industrial-amber.css`:**

Selektor: `[data-theme="industrial-amber"]`

Dunkles Amber/Industrie-Thema (alle semantischen Tokens überschreiben):
```css
--color-bg: #0d0a00;
--color-surface: #1a1200;
--color-surface-alt: #231800;
--color-border: #4a3000;
--color-text: #fff3d0;
--color-text-muted: #a08040;
--color-accent: #ffaa00;
--color-accent-2: #ff6b00;
--color-success: #80ff40;
--color-warning: #ffdd00;
--color-danger: #ff3300;
```

**3. `frontend/src/design/themes/operator-mono.css`:**

Selektor: `[data-theme="operator-mono"]`

High-Contrast Monochrom-Thema:
```css
--color-bg: #000000;
--color-surface: #0a0a0a;
--color-surface-alt: #141414;
--color-border: #333333;
--color-text: #f0f0f0;
--color-text-muted: #888888;
--color-accent: #ffffff;
--color-accent-2: #cccccc;
--color-success: #00ff00;
--color-warning: #ffff00;
--color-danger: #ff0000;
```

**4. `frontend/src/composables/useTheme.ts`:**

```ts
import { ref, watch } from 'vue'

type Theme = 'space-neon' | 'industrial-amber' | 'operator-mono'

const STORAGE_KEY = 'hivemind-theme'
const DEFAULT_THEME: Theme = 'space-neon'

const availableThemes: Theme[] = ['space-neon', 'industrial-amber', 'operator-mono']

const stored = localStorage.getItem(STORAGE_KEY) as Theme | null
const currentTheme = ref<Theme>(stored ?? DEFAULT_THEME)

// Initial anwenden
document.documentElement.dataset.theme = currentTheme.value

function setTheme(theme: Theme) {
  currentTheme.value = theme
  document.documentElement.dataset.theme = theme
  localStorage.setItem(STORAGE_KEY, theme)
}

export function useTheme() {
  return { currentTheme, availableThemes, setTheme }
}
```

**5. Alle drei Theme-CSS-Dateien in `frontend/src/main.ts` nach den Design-Token-Importen importieren:**
```ts
import './design/themes/space-neon.css'
import './design/themes/industrial-amber.css'
import './design/themes/operator-mono.css'
```

### Definition of Done

- [ ] Alle drei Theme-CSS-Dateien existieren mit vollständig definierten semantischen Token-Überschreibungen
- [ ] `space-neon.css` enthält exakt die spezifizierten Referenzfarbwerte
- [ ] `useTheme()` Composable ist in `src/composables/useTheme.ts` exportiert
- [ ] `setTheme('industrial-amber')` wechselt `document.documentElement.dataset.theme` korrekt
- [ ] Theme-Wahl überlebt Page-Reload (localStorage-Persistenz)
- [ ] Seite rendert mit `space-neon`-Theme als Default wenn kein localStorage-Wert gesetzt

### Einschränkungen

- Kein Vue-SFC in den Theme-CSS-Dateien — nur CSS Custom Properties
- Der `useTheme`-Composable ist ein Singleton (Module-Level-State, kein `provide/inject` nötig)
```

---

## TASK-1B-005 — Accessibility-Baseline im Design System

```
## Rolle: Worker

Du arbeitest an TASK-1B-005 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-003 und TASK-1B-004 abgeschlossen.

### Dein Auftrag

Accessibility-Grundlagen direkt im CSS-Design-System verankern.

**1. `frontend/src/design/tokens.css` erweitern** (am Ende des `:root`-Blocks anhängen):
```css
/* Focus Ring */
--focus-ring-color: #20e3ff;
--focus-ring-width: 2px;
--focus-ring-offset: 2px;

/* Reduced Motion */
@media (prefers-reduced-motion: reduce) {
  :root {
    --transition-duration: 0ms;
    --animation-duration: 0ms;
  }
}
```

**2. Alle drei Theme-Dateien erweitern** — jeweils `--focus-ring-color` mit einem High-Contrast-Wert für das Theme überschreiben:
- `space-neon.css`: `--focus-ring-color: #20e3ff;` (accent-Farbe)
- `industrial-amber.css`: `--focus-ring-color: #ffaa00;` (amber accent)
- `operator-mono.css`: `--focus-ring-color: #ffffff;` (reines Weiß auf Schwarz)

**3. `frontend/src/design/components.css` erweitern** (am Ende anhängen):
```css
/* Accessibility: Focus Ring */
:focus-visible {
  outline: var(--focus-ring-width) solid var(--focus-ring-color);
  outline-offset: var(--focus-ring-offset);
}

:focus:not(:focus-visible) {
  outline: none;
}

/* Interaktive Elemente erben den Ring */
a, button, input, select, textarea, [tabindex] {
  /* Focus-Ring wird durch :focus-visible oben gesetzt */
}
```

### Definition of Done

- [ ] `--focus-ring-color`, `--focus-ring-width`, `--focus-ring-offset` sind in `tokens.css` definiert
- [ ] `@media (prefers-reduced-motion: reduce)` Block ist in `tokens.css` vorhanden
- [ ] Jede Theme-Datei überschreibt `--focus-ring-color` mit einem für das Theme geeigneten High-Contrast-Wert
- [ ] `components.css` enthält `:focus-visible`-Regel mit `outline: var(--focus-ring-width) solid var(--focus-ring-color)`
- [ ] Tab-Navigation auf der leeren App-Seite zeigt sichtbaren Focus-Ring auf fokussierten Elementen

### Einschränkungen

- Nur CSS-Änderungen — keine Vue-Dateien
- Kein `outline: none` auf `:focus` ohne gleichzeitig `:focus-visible` zu bedienen
```

---

## TASK-1B-006 — Layout Shell — AppShell.vue mit 5-Slot CSS-Grid

```
## Rolle: Worker

Du arbeitest an TASK-1B-006 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-001 (Scaffold) und TASK-1B-003 (Design-Tokens) abgeschlossen.

### Dein Auftrag

`frontend/src/components/layout/AppShell.vue` implementieren — die strukturelle Hülle der gesamten App.

**Anforderungen:**

1. **CSS Grid Layout** (kein Flexbox):
   - Grid-Areas: `system-bar`, `nav-sidebar`, `main-canvas`, `context-panel`, `status-bar`
   - Grid-Template:
     ```
     "system-bar   system-bar   system-bar"  var(--systembar-height)
     "nav-sidebar  main-canvas  context-panel" 1fr
     "status-bar   status-bar   status-bar"  var(--statusbar-height)
     ```
   - NavSidebar-Breite: `var(--sidebar-width)` (collapsed: `var(--sidebar-collapsed-width)`)
   - ContextPanel-Breite: `320px` (collapsed: `0`)
   - Transition: `width var(--transition-duration) ease, grid-template-columns var(--transition-duration) ease`

2. **Fünf benannte Slots:**
   ```html
   <slot name="system-bar" />
   <slot name="nav-sidebar" />
   <slot name="main-canvas" />
   <slot name="context-panel" />
   <slot name="status-bar" />
   ```

3. **Props:**
   ```ts
   const props = withDefaults(defineProps<{
     navCollapsed?: boolean
     contextCollapsed?: boolean
   }>(), { navCollapsed: false, contextCollapsed: true })
   ```

4. **Alle Farben via Design-Tokens** — kein einziger hardcodierter Hex-Wert.

5. **AppShell in `frontend/src/App.vue` einbinden:**
   ```vue
   <AppShell>
     <template #system-bar><!-- SystemBar Placeholder --></template>
     <template #nav-sidebar><!-- NavSidebar Placeholder --></template>
     <template #main-canvas><RouterView /></template>
     <template #context-panel><!-- ContextPanel Placeholder --></template>
     <template #status-bar><!-- StatusBar Placeholder --></template>
   </AppShell>
   ```
   Placeholder-Inhalte: einfache `<div>` mit Hintergrundfarbe aus Token und minimalem Padding.

### Definition of Done

- [ ] `src/components/layout/AppShell.vue` existiert und ist in `App.vue` eingebunden
- [ ] Alle 5 benannten Slots sind vorhanden
- [ ] CSS Grid definiert alle 5 Areas korrekt — kein Overflow, kein Scrolling-Fehler
- [ ] NavSidebar collapsed-State reduziert die Breite via CSS-Transition auf `--sidebar-collapsed-width`
- [ ] ContextPanel collapsed-State blendet das Panel via CSS-Transition aus
- [ ] `<RouterView />` rendert korrekt im `main-canvas`-Slot
- [ ] Alle Farben kommen aus Design-Tokens — keine hardcodierten Hex-Werte

### Einschränkungen

- Nur das Layout-Gerüst — kein Inhalt, keine Navigation-Links (kommen in TASK-1B-008)
- `main-canvas` muss `overflow-y: auto` haben (scrollbarer Hauptbereich)
- AppShell bricht nicht wenn Slots leer sind
```

---

## TASK-1B-007 — Layer 2 UI Primitives — HivemindCard, HivemindModal, HivemindDropdown

```
## Rolle: Worker

Du arbeitest an TASK-1B-007 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-001 (Scaffold inkl. @reka-ui/core) und TASK-1B-003 (Component-Tokens) abgeschlossen.

### Dein Auftrag

Drei Reka UI Wrapper-Komponenten in `frontend/src/components/ui/` erstellen.
Kein Domain-Wissen — keine Begriffe wie Epic, Task, Skill in diesen Dateien.
Alle Styles ausschließlich via Component-Tokens aus `components.css`.

**1. `HivemindCard.vue`:**
```vue
<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'default' | 'elevated' | 'outlined'
}>(), { variant: 'default' })
</script>

<template>
  <div class="hm-card" :class="`hm-card--${variant}`">
    <slot />
  </div>
</template>

<style scoped>
.hm-card {
  background: var(--card-bg);
  border: var(--card-border);
  border-radius: var(--card-radius);
  padding: var(--space-4);
}
.hm-card--elevated { box-shadow: var(--shadow-md); }
.hm-card--outlined { background: transparent; }
</style>
```

**2. `HivemindModal.vue`:**
- Reka UI `DialogRoot`, `DialogPortal`, `DialogOverlay`, `DialogContent`, `DialogTitle` verwenden
- Props: `modelValue: boolean`, `title?: string`, `size?: 'sm' | 'md' | 'lg'` (default `'md'`)
- Emit: `update:modelValue`
- Slot: `default` (Body), benannter Slot `footer`
- Backdrop: `var(--modal-backdrop)`, Box: `var(--modal-bg)`
- Escape-Key-Close und Fokus-Trap werden von Reka UI `Dialog` automatisch gehandhabt
- Größen: `sm: 400px`, `md: 560px`, `lg: 760px` max-width

**3. `HivemindDropdown.vue`:**
- Reka UI `DropdownMenuRoot`, `DropdownMenuTrigger`, `DropdownMenuContent`, `DropdownMenuItem` verwenden
- Props: `items: Array<{ label: string; value: string; icon?: string; disabled?: boolean }>`, `modelValue?: string`
- Emit: `update:modelValue`
- Slot `trigger`: der auslösende Button/Element
- Items via `v-for` rendern, bei Klick `emit('update:modelValue', item.value)`
- Styling via Component-Tokens

**4. `frontend/src/components/ui/index.ts`:**
```ts
export { default as HivemindCard } from './HivemindCard.vue'
export { default as HivemindModal } from './HivemindModal.vue'
export { default as HivemindDropdown } from './HivemindDropdown.vue'
```

### Definition of Done

- [ ] Alle drei Dateien existieren in `src/components/ui/`
- [ ] `src/components/ui/index.ts` re-exportiert alle drei
- [ ] HivemindModal öffnet/schließt via v-model, Escape-Key schließt das Modal
- [ ] HivemindModal hat funktionierenden Fokus-Trap
- [ ] HivemindDropdown rendert Items und emittiert `update:modelValue`
- [ ] Keine hardcodierten Farb-/Größenwerte — ausschließlich Component-Tokens
- [ ] Keine Domain-Begriffe in den Dateien

### Einschränkungen

- Reka UI API für Dialog: `@reka-ui/core` — Komponenten heißen `DialogRoot`, `DialogContent`, etc.
- Falls Reka UI keine DropdownMenu-Primitive hat, Reka UI `SelectRoot` oder natives `<select>` als Fallback nutzen und das im Result-Kommentar dokumentieren
```

---

## TASK-1B-008 — Vue Router Setup + View-Platzhalter für alle Routes

```
## Rolle: Worker

Du arbeitest an TASK-1B-008 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-001 (Scaffold + Router bootstrapped), TASK-1B-006 (AppShell mit NavSidebar-Slot) abgeschlossen.

### Dein Auftrag

Router-Config anlegen und alle Views als Platzhalter erstellen.

**1. `frontend/src/router/index.ts`:**
```ts
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',             component: () => import('../views/PromptStation/PromptStationView.vue') },
    { path: '/command-deck', component: () => import('../views/CommandDeck/CommandDeckView.vue') },
    { path: '/skill-lab',    component: () => import('../views/SkillLab/SkillLabView.vue') },
    { path: '/wiki',         component: () => import('../views/Wiki/WikiView.vue') },
    { path: '/settings',     component: () => import('../views/Settings/SettingsView.vue') },
    { path: '/notifications',component: () => import('../views/NotificationTray/NotificationTrayView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
```

Den Router in `main.ts` via `app.use(router)` registrieren (falls noch nicht in TASK-1B-001 geschehen).

**2. View-Platzhalter anlegen** (Verzeichnis + Datei):

- `src/views/PromptStation/PromptStationView.vue` — zeigt `<h1>Prompt Station</h1>` + TODO-Kommentar (wird in TASK-1B-010 ersetzt)
- `src/views/CommandDeck/CommandDeckView.vue` — **Lock-Teaser**: Schloss-Icon (🔒) + Text "Command Deck — Verfügbar in Phase 2"
- `src/views/SkillLab/SkillLabView.vue` — **Lock-Teaser**: 🔒 + "Skill Lab — Verfügbar in Phase 2"
- `src/views/Wiki/WikiView.vue` — **Lock-Teaser**: 🔒 + "Wiki — Verfügbar in Phase 2"
- `src/views/Settings/SettingsView.vue` — zeigt `<h1>Settings</h1>` + TODO-Kommentar (wird in TASK-1B-012 ersetzt)
- `src/views/NotificationTray/NotificationTrayView.vue` — zeigt `<h1>Notifications</h1>` + TODO-Kommentar

**3. Nav-Links in AppShell NavSidebar-Slot** (in `frontend/src/App.vue`):

Den NavSidebar-Placeholder durch echte `<RouterLink>`-Liste ersetzen:
```html
<template #nav-sidebar>
  <nav class="app-nav">
    <RouterLink to="/">Prompt Station</RouterLink>
    <RouterLink to="/command-deck">Command Deck 🔒</RouterLink>
    <RouterLink to="/skill-lab">Skill Lab 🔒</RouterLink>
    <RouterLink to="/wiki">Wiki 🔒</RouterLink>
    <RouterLink to="/settings">Settings</RouterLink>
    <RouterLink to="/notifications">Notifications</RouterLink>
  </nav>
</template>
```
Minimales Styling via Design-Tokens (kein Inline-Style).

### Definition of Done

- [ ] `src/router/index.ts` existiert mit allen 6 Routes
- [ ] Alle 6 View-Dateien existieren als Platzhalter in ihren Unterordnern
- [ ] CommandDeck-, SkillLab-, Wiki-Views zeigen Lock-Teaser
- [ ] Navigation funktioniert via URL und RouterLink
- [ ] 404 → Redirect auf `/`

### Einschränkungen

- Platzhalter-Views enthalten weder API-Calls noch Stores — nur statisches Template
- Lock-Teaser-Views haben korrekte `<RouterLink to="/">`-Zurück-Links
```

---

## TASK-1B-009 — API Client Integration — Adapter-Shim + Typen

```
## Rolle: Worker

Du arbeitest an TASK-1B-009 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-001 und TASK-1B-002 abgeschlossen.

### Dein Auftrag

`frontend/src/api/index.ts` als zentralen Adapter-Shim implementieren.

**1. Temporäre Typ-Definitionen** (bis `generate:api` gelaufen ist) in `frontend/src/api/types.ts`:
```ts
export interface Project {
  id: string
  name: string
  slug: string
  description?: string
  created_at: string
}

export interface Epic {
  id: string
  project_id: string
  title: string
  state: 'incoming' | 'scoped' | 'in_progress' | 'done' | 'cancelled'
  priority: 'low' | 'medium' | 'high' | 'critical'
  sla_deadline?: string
  definition_of_done?: { criteria: string[] }
}

export interface Task {
  id: string
  epic_id: string
  title: string
  description: string
  state: 'incoming' | 'scoped' | 'ready' | 'in_progress' | 'in_review' | 'done' | 'qa_failed' | 'blocked' | 'escalated' | 'cancelled'
  priority: 'low' | 'medium' | 'high' | 'critical'
  definition_of_done?: { criteria: string[] }
}
```

**2. `frontend/src/api/index.ts`:**
```ts
import type { Project, Epic, Task } from './types'

const BASE_URL = (import.meta.env.VITE_API_URL as string) ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `HTTP ${res.status}: ${path}`)
  }
  return res.json()
}

export const api = {
  getProjects: () =>
    request<Project[]>('/api/projects'),

  createProject: (data: { name: string; slug: string; description?: string }) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(data) }),

  getEpics: (projectId: string) =>
    request<Epic[]>(`/api/epics?project_id=${projectId}`),

  patchEpicState: (epicId: string, patch: { state: string; priority?: string; sla_deadline?: string; dod?: string }) =>
    request<Epic>(`/api/epics/${epicId}/state`, { method: 'PATCH', body: JSON.stringify(patch) }),

  getTasks: (epicId: string) =>
    request<Task[]>(`/api/tasks?epic_id=${epicId}`),

  approveTask: (taskId: string) =>
    request<Task>(`/api/tasks/${taskId}/approve`, { method: 'POST' }),

  rejectTask: (taskId: string, comment?: string) =>
    request<Task>(`/api/tasks/${taskId}/reject`, { method: 'POST', body: JSON.stringify({ comment }) }),
}
```

**3. `frontend/vite.config.ts` um Proxy erweitern:**
```ts
server: {
  proxy: {
    '/api': {
      target: process.env.VITE_API_URL ?? 'http://localhost:8000',
      changeOrigin: true,
    },
  },
},
```

**4. `frontend/.env.example` anlegen:**
```
VITE_API_URL=http://localhost:8000
```

### Definition of Done

- [ ] `src/api/index.ts` existiert und exportiert alle 7 spezifizierten API-Funktionen via `api`-Objekt
- [ ] `src/api/types.ts` existiert mit Project-, Epic-, Task-Interfaces
- [ ] Basis-URL aus `import.meta.env.VITE_API_URL` mit Fallback
- [ ] `vite.config.ts` hat Proxy-Konfiguration `/api` → `VITE_API_URL`
- [ ] `frontend/.env.example` existiert
- [ ] TypeScript-Compilation ohne Fehler

### Einschränkungen

- Kein direktes Importieren von `src/api/client/` — der Shim kapselt alles
- Error-Handling: HTTP-Fehler immer als sprechende Exception werfen (Backend-`detail`-Feld nutzen)
```

---

## TASK-1B-010 — Prompt Station View — Inline-Review + Inline-Scoping

```
## Rolle: Worker

Du arbeitest an TASK-1B-010 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-006 (AppShell), TASK-1B-007 (UI Primitives), TASK-1B-008 (Router, View-Platzhalter), TASK-1B-009 (API Shim) abgeschlossen.

### Dein Auftrag

`frontend/src/views/PromptStation/PromptStationView.vue` vollständig implementieren (ersetzt den Platzhalter).
Zusätzlich: `frontend/src/stores/projectStore.ts` anlegen.

**1. Pinia-Store `frontend/src/stores/projectStore.ts`:**
```ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api'
import type { Project, Epic, Task } from '../api/types'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const activeProject = ref<Project | null>(null)
  const activeEpic = ref<Epic | null>(null)
  const activeTask = ref<Task | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadProjects() {
    loading.value = true
    try {
      projects.value = await api.getProjects()
      if (projects.value.length > 0 && !activeProject.value) {
        await setActiveProject(projects.value[0])
      }
    } catch (e: any) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function setActiveProject(project: Project) {
    activeProject.value = project
    const epics = await api.getEpics(project.id)
    // Erstes nicht-done, nicht-cancelled Epic nehmen
    activeEpic.value = epics.find(e => !['done', 'cancelled'].includes(e.state)) ?? epics[0] ?? null
    if (activeEpic.value) {
      const tasks = await api.getTasks(activeEpic.value.id)
      activeTask.value = tasks.find(t => ['in_progress', 'in_review'].includes(t.state)) ?? tasks[0] ?? null
    }
  }

  async function refreshActiveTask() {
    if (!activeEpic.value) return
    const tasks = await api.getTasks(activeEpic.value.id)
    activeTask.value = tasks.find(t => t.id === activeTask.value?.id) ?? null
  }

  return { projects, activeProject, activeEpic, activeTask, loading, error, loadProjects, setActiveProject, refreshActiveTask }
})
```

**2. `PromptStationView.vue` — Aufbau:**

Die View hat vier bedingte Sections:

**(A) Leer-State** (wenn `activeProject === null` nach dem Laden):
```html
<div class="prompt-station__empty">
  <p>Kein Projekt aktiv.</p>
  <button @click="showCreateDialog = true">+ Projekt anlegen</button>
  <ProjectCreateDialog v-model="showCreateDialog" />
</div>
```

**(B) Aktiver Task** (wenn `activeTask !== null`):
```html
<HivemindCard class="prompt-station__task">
  <h2>{{ activeTask.title }}</h2>
  <p>{{ activeTask.description }}</p>
  <button @click="copyToClipboard(activeTask.description)">📋 Kopieren</button>
  <span class="task-state">{{ activeTask.state }}</span>
</HivemindCard>
```
`copyToClipboard`: `navigator.clipboard.writeText(text)`

**(C) Inline-Review-Panel** (nur wenn `activeTask.state === 'in_review'`):
```html
<HivemindCard class="prompt-station__review">
  <h3>Review: {{ activeTask.title }}</h3>
  <!-- DoD-Checkliste (nur UI-State, kein Backend-Write) -->
  <ul>
    <li v-for="(criterion, i) in activeTask.definition_of_done?.criteria ?? []" :key="i">
      <input type="checkbox" v-model="checkedCriteria[i]" /> {{ criterion }}
    </li>
  </ul>
  <textarea v-model="reviewComment" placeholder="Kommentar (optional)" />
  <div class="review-actions">
    <button class="btn-danger" @click="handleReject" :disabled="reviewLoading">✗ ABLEHNEN</button>
    <button class="btn-success" @click="handleApprove" :disabled="reviewLoading">✓ GENEHMIGEN</button>
  </div>
</HivemindCard>
```
`handleApprove`: `api.approveTask(activeTask.id)` → `refreshActiveTask()`
`handleReject`: `api.rejectTask(activeTask.id, reviewComment)` → `refreshActiveTask()`

**(D) Inline-Scoping-Panel** (nur wenn `activeEpic.state === 'incoming'`):
```html
<HivemindCard class="prompt-station__scoping">
  <h3>Epic scopen: {{ activeEpic.title }}</h3>
  <HivemindDropdown
    :items="priorityOptions"
    v-model="scopingPriority"
  >
    <template #trigger><button>Priorität: {{ scopingPriority }}</button></template>
  </HivemindDropdown>
  <input type="date" v-model="scopingSlaDeadline" />
  <textarea v-model="scopingDod" placeholder="Definition of Done (Kurztext)" />
  <button @click="handleScope" :disabled="scopingLoading">EPIC SCOPEN →</button>
</HivemindCard>
```
`handleScope`: `api.patchEpicState(activeEpic.id, { state: 'scoped', priority: scopingPriority, sla_deadline: scopingSlaDeadline, dod: scopingDod })`

**3. `onMounted`:** `projectStore.loadProjects()` aufrufen.

**4. `frontend/src/components/domain/`-Ordner anlegen** (für TASK-1B-011). Die View importiert `ProjectCreateDialog` aus diesem Verzeichnis — eine Stub-Datei anlegen falls TASK-1B-011 noch läuft.

### Definition of Done

- [ ] View zeigt 'Kein Projekt aktiv' Leer-State mit ProjectCreateDialog-Trigger
- [ ] Aktiver Task wird angezeigt mit Kopieren-Button der in Clipboard schreibt
- [ ] Inline-Review-Panel erscheint NUR wenn Task-State `in_review`
- [ ] GENEHMIGEN ruft `approveTask()` auf und lädt Task danach neu
- [ ] ABLEHNEN ruft `rejectTask()` mit optionalem Kommentar auf
- [ ] Inline-Scoping-Panel erscheint NUR wenn Epic-State `incoming`
- [ ] EPIC-SCOPEN sendet korrekte PATCH-Anfrage und aktualisiert Epic-State  
- [ ] `src/stores/projectStore.ts` existiert
- [ ] Alle Styles via Component-Tokens

### Einschränkungen

- Beide Panels (Review + Scoping) dürfen NICHT gleichzeitig sichtbar sein — sie schließen sich gegenseitig aus (aktiver Task in_review → Review-Panel; aktives Epic incoming → Scoping-Panel; beides nie gleichzeitig)
- Loading-States bei allen API-Calls (Buttons disabled während Request läuft)
- Fehler-States anzeigen (Toast oder Inline-Fehlermeldung)
```

---

## TASK-1B-011 — Projekt-Anlegen-Dialog (ProjectCreateDialog)

```
## Rolle: Worker

Du arbeitest an TASK-1B-011 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-007 (HivemindModal), TASK-1B-009 (API Shim) abgeschlossen.

### Dein Auftrag

`frontend/src/components/domain/ProjectCreateDialog.vue` implementieren.

Domain-Komponente (Layer 3 — kennt Hivemind-Konzepte). Basiert auf `HivemindModal`.

**Props & Emits:**
```ts
const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
```

**Formular-Felder:**
1. **Name** — text input, required, maxlength 100, `@input` triggert Slug-Auto-Generierung
2. **Slug** — text input, auto-generiert, editierbar, validiert:
   ```ts
   function generateSlug(name: string): string {
     return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
   }
   watch(name, (val) => { if (!slugManuallyEdited.value) slug.value = generateSlug(val) })
   ```
   Pattern-Validierung: `/^[a-z0-9-]+$/` — Fehlermeldung "Nur Kleinbuchstaben, Zahlen und Bindestriche"
3. **Beschreibung** — textarea, optional, maxlength 500

**Submit:**
```ts
async function handleSubmit() {
  if (!name.value || !slug.value) return
  loading.value = true
  error.value = null
  try {
    const project = await api.createProject({ name: name.value, slug: slug.value, description: description.value })
    projectStore.projects.push(project)
    await projectStore.setActiveProject(project)
    emit('update:modelValue', false)
    // Formular reset
    name.value = ''; slug.value = ''; description.value = ''; slugManuallyEdited.value = false
  } catch (e: any) {
    if (e.message.includes('409') || e.message.toLowerCase().includes('conflict')) {
      slugError.value = 'Dieser Slug ist bereits vergeben.'
    } else {
      error.value = e.message
    }
  } finally {
    loading.value = false
  }
}
```

**Template-Struktur:**
```html
<HivemindModal :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)" title="Neues Projekt anlegen">
  <form @submit.prevent="handleSubmit">
    <label>Name <input v-model="name" required maxlength="100" /></label>
    <label>
      Slug
      <input v-model="slug" @input="slugManuallyEdited = true" pattern="[a-z0-9-]+" />
      <span v-if="slugError" class="field-error">{{ slugError }}</span>
    </label>
    <label>Beschreibung <textarea v-model="description" maxlength="500" /></label>
    <span v-if="error" class="form-error">{{ error }}</span>
  </form>
  <template #footer>
    <button type="button" @click="emit('update:modelValue', false)">Abbrechen</button>
    <button type="submit" @click="handleSubmit" :disabled="loading || !name || !slug">
      {{ loading ? '...' : 'PROJEKT ANLEGEN' }}
    </button>
  </template>
</HivemindModal>
```

### Definition of Done

- [ ] Datei existiert und öffnet als HivemindModal
- [ ] Slug wird automatisch aus Namen generiert und aktualisiert sich
- [ ] Slug-Feld validiert `[a-z0-9-]` Format
- [ ] Submit ruft `createProject()` auf und setzt neues Projekt als aktiv im Store
- [ ] 409-Fehler zeigt Fehlermeldung unter dem Slug-Feld
- [ ] Loading-State während API-Call: Button disabled
- [ ] Komponente aufrufbar via `v-model` aus Prompt Station und System Bar

### Einschränkungen

- Komponente importiert `useProjectStore` — Store muss vor erster Nutzung initialisiert sein (Pinia registriert in main.ts)
- Formular-Reset nach erfolgreichem Submit
- Keine Page-Navigation nach Submit — Modal schließen genügt
```

---

## TASK-1B-012 — Settings View — Theme, Solo/Team, MCP-Transport

```
## Rolle: Worker

Du arbeitest an TASK-1B-012 im Rahmen von EPIC-PHASE-1B.
Voraussetzung: TASK-1B-004 (Theme Engine + useTheme), TASK-1B-007 (HivemindDropdown), TASK-1B-008 (Router / SettingsView Platzhalter) abgeschlossen.

### Dein Auftrag

`frontend/src/views/Settings/SettingsView.vue` vollständig implementieren (ersetzt Platzhalter).
Zusätzlich: `frontend/src/stores/settingsStore.ts` anlegen.

**1. `frontend/src/stores/settingsStore.ts`:**
```ts
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

type AppMode = 'solo' | 'team'
type McpTransport = 'stdio' | 'http' | 'sse'

const STORAGE_KEY = 'hivemind-settings'

function load() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') } catch { return {} }
}

export const useSettingsStore = defineStore('settings', () => {
  const saved = load()
  const mode = ref<AppMode>(saved.mode ?? 'solo')
  const mcpTransport = ref<McpTransport>(saved.mcpTransport ?? 'stdio')

  watch([mode, mcpTransport], () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode: mode.value, mcpTransport: mcpTransport.value }))
  })

  return { mode, mcpTransport }
})
```

**2. `SettingsView.vue` — drei Einstellungsbereiche:**

**(A) Theme-Auswahl:**
```html
<section class="settings-section">
  <h2>Theme</h2>
  <div class="theme-picker">
    <button
      v-for="theme in availableThemes"
      :key="theme"
      class="theme-card"
      :class="{ 'theme-card--active': currentTheme === theme }"
      @click="setTheme(theme)"
    >
      <div class="theme-preview" :data-preview-theme="theme">
        <span class="theme-name">{{ theme }}</span>
        <!-- 3 Farbdots: accent, bg, surface -->
      </div>
    </button>
  </div>
</section>
```
Jede Theme-Card hat einen Mini-Farbstreifen aus den Theme-Farben (kein CSS-in-JS — via `data-preview-theme`-Attribut und CSS-Selektoren).

**(B) Solo/Team-Toggle:**
```html
<section class="settings-section">
  <h2>Modus</h2>
  <p>Solo: Du bist der einzige Nutzer. Team: Mehrere Nutzer, RBAC aktiv (ab Phase 2).</p>
  <label class="toggle-label">
    <input type="checkbox" :checked="settingsStore.mode === 'team'"
      @change="settingsStore.mode = ($event.target as HTMLInputElement).checked ? 'team' : 'solo'" />
    {{ settingsStore.mode === 'solo' ? 'Solo-Modus' : 'Team-Modus' }}
  </label>
</section>
```

**(C) MCP-Transport:**
```html
<section class="settings-section">
  <h2>MCP-Transport</h2>
  <p class="settings-note">MCP-Backend-Anbindung ab Phase 2.</p>
  <HivemindDropdown
    :items="[
      { label: 'stdio (lokal)', value: 'stdio' },
      { label: 'HTTP', value: 'http' },
      { label: 'SSE', value: 'sse' },
    ]"
    v-model="settingsStore.mcpTransport"
  >
    <template #trigger>
      <button>Transport: {{ settingsStore.mcpTransport }}</button>
    </template>
  </HivemindDropdown>
</section>
```

**3. Script:**
```ts
import { useTheme } from '../../composables/useTheme'
import { useSettingsStore } from '../../stores/settingsStore'
import { HivemindDropdown } from '../../components/ui'

const { currentTheme, availableThemes, setTheme } = useTheme()
const settingsStore = useSettingsStore()
```

### Definition of Done

- [ ] View existiert mit allen drei Einstellungsbereichen
- [ ] Theme-Auswahl wechselt Theme live via `setTheme()` — sofort visuell sichtbar
- [ ] Aktives Theme ist hervorgehoben
- [ ] Solo/Team-Toggle speichert Wert im `settingsStore` und überlebt Page-Reload
- [ ] MCP-Transport-Dropdown zeigt `stdio`, `http`, `sse` und speichert Wahl
- [ ] `src/stores/settingsStore.ts` existiert und persistiert in localStorage

### Einschränkungen

- Kein Backend-Call in dieser View — alle Werte nur in localStorage via settingsStore
- Theme-Vorschau-Cards müssen das aktive Theme hervorheben ohne globale Styles zu überschreiben
- `settingsStore.theme` wird NICHT im settingsStore gespeichert — `useTheme()` Composable hat eigene localStorage-Persistenz
```
