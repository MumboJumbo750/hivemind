---
slug: "frontend-component-architektur"
title: "Frontend Component-Architektur — Refactoring-Strategie"
tags: ["frontend", "vue3", "design-system", "architektur", "refactoring"]
linked_epics: []
---

# Frontend Component-Architektur — Refactoring-Strategie

## Problem-Analyse

### Ist-Zustand (quantitativ)

| Problem | Ausmaß |
| --- | --- |
| Button-Styles (`.btn-primary`, `.btn-sm`, …) | **11+ Views** re-definieren eigene Button-Klassen |
| Badge/Pill-Pattern | **~30 Varianten** über Views verstreut (Status, Source, State, Priority) |
| Hardcoded `border-radius` | **~50 %** nutzen `3px`/`4px`/`8px` statt `var(--radius-*)` |
| Hardcoded `padding` | **69 Stellen** mit Pixel-Werten statt `var(--space-*)` |
| Hardcoded Hex-Farben / `rgba()` | **~40 %** der `background`-Deklarationen ohne Token-Referenz |
| Component-Token-Adoption | `--button-primary-*` existiert, wird aber **nur in 1 File** genutzt |

### Beispiel: Button-Duplikation

Diese Views definieren alle ihr eigenes `.btn-primary`:

```
PromptStationView, TriageStationView, SkillLabView,
NotificationTrayView, KartographBootstrapView, SettingsView,
WikiView, TaskReviewPanel, RequirementCaptureModal,
McpBridgeConfigPanel, GovernanceConfigPanel, FederationSettings,
EpicScopingModal
```

Jede Instanz hat leicht unterschiedliche `padding`, `border-radius`, `:hover`-Effekte.

### Beispiel: Badge-Duplikation

Das Pattern `rgba(color, 0.2)` + farbiger Text + `padding: 2px 8px` + `border-radius: 3px` + `font-size: 0.65rem` + `text-transform: uppercase` wiederholt sich in:

- CommandDeckView: `badge--pending`, `badge--done`, `badge--active`, etc.
- TriageStationView: `badge-youtrack`, `badge-sentry`, `badge-federation`, `state-unrouted`, `state-routed`, `badge-proposed`, `badge-accepted`
- SkillLabView: Lifecycle-Badges (draft, pending_merge, active, deprecated)
- QueueBadge: Eigenständig, aber ebenfalls hardcoded

---

## Was bereits existiert

### Design Token System (3 Schichten)

Das Token-System ist **gut entworfen**, aber unter-genutzt:

| Datei | Inhalt |
| --- | --- |
| `frontend/src/design/tokens.css` | Primitiven: Farb-Paletten, `--space-*`, `--font-size-*`, `--radius-*`, `--shadow-*`, `--z-*`, Focus-Ring, Transitions |
| `frontend/src/design/semantic.css` | Semantische Farben: `--color-bg`, `--color-surface`, `--color-accent`, `--color-success/warning/danger` |
| `frontend/src/design/components.css` | Component-Tokens: `--button-primary-*`, `--card-*`, `--input-*`, `--modal-*`, `--sidebar-*` + Focus-Ring |
| 3 Theme-Dateien | `space-neon.css`, `industrial-amber.css`, `operator-mono.css` |

### Vorhandene UI-Components (8 Stück)

| Component | Qualität |
| --- | --- |
| `HivemindCard` | ✅ Exemplarisch — 100 % Token-gesteuert, 3 Varianten |
| `HivemindDropdown` | ✅ Reka-UI-Wrapper, fast vollständig tokenisiert |
| `HivemindModal` | ✅ Reka-UI-Wrapper, gute Token-Nutzung |
| `TokenRadar` | ◐ Spezialisiert, eigene Styles |
| `ToastContainer` | ◐ Funktional, einige Hardcodes |
| `SlaCountdown` | ◐ Timer-Logik + eigene Badge-Styles |
| `QueueBadge` | ⚠ Hardcoded Farben und Padding |
| `McpStatusIndicator` | ⚠ Mix aus Tokens und Hardcodes |

### Vorhandene Skills

| Skill | Relevanz |
| --- | --- |
| `design-token` | Token-Konventionen (Naming, Kategorien, Theme-Switch) |
| `vue-component` | 4-Schichten-Modell, `Hv`-Prefix, Composition API Regeln |

**Lücke:** Es fehlen Skills für **Component Extraction** (wann/wie man ein wiederkehrendes Pattern in ein wiederverwendbares Component extrahiert) und **Design System Compliance** (Regel: „niemals hardcoded Werte, immer Token-Referenz").

---

## Vorgeschlagene neue Micro-Components

### Tier 1 — Sofort extrahierbar (höchster ROI)

| Component | Props | Eliminiert |
| --- | --- | --- |
| `HmButton` | `variant: 'primary' \| 'secondary' \| 'danger' \| 'ghost'`, `size: 'sm' \| 'md' \| 'lg'`, `loading`, `disabled`, `icon` | ~11 duplizierte `.btn`-Blöcke |
| `HmBadge` | `variant: 'success' \| 'warning' \| 'danger' \| 'info' \| 'neutral'`, `size: 'xs' \| 'sm'`, `uppercase` | ~30 Badge/Pill-Definitionen |
| `HmInput` | `type`, `placeholder`, `modelValue`, `error`, `disabled` | ~8 Input-Style-Blöcke |
| `HmFormGroup` | `label`, `hint`, `error`, `required` | Label+Input-Wrapper in jedem Formular |

### Tier 2 — Domain-Aware Micro-Components

| Component | Props | Nutzt |
| --- | --- | --- |
| `HmStateBadge` | `state: TaskState \| EpicState`, `entity: 'task' \| 'epic'` | → `HmBadge` intern |
| `HmSourceBadge` | `source: 'youtrack' \| 'sentry' \| 'federation' \| 'manual'` | → `HmBadge` intern |
| `HmPriorityBadge` | `priority: 'low' \| 'medium' \| 'high' \| 'critical'` | → `HmBadge` intern |
| `HmIconButton` | `icon`, `tooltip`, `variant` | → `HmButton` mit nur Icon |
| `HmEmptyState` | `icon`, `title`, `description`, `action?` | Leere-Liste-Fallback |

### Tier 3 — Layout-Composables

| Component | Zweck |
| --- | --- |
| `HmToolbar` | Flex-Row für Action-Buttons + Filter |
| `HmSplitView` | Sidebar + Main Content Pattern |
| `HmKeyValue` | Key-Value-Zeile (`label: value`) für Detail-Panels |
| `HmSectionHeader` | Abschnitt-Header mit optionalem Action-Slot |

---

## Naming- und Datei-Konventionen

```
frontend/src/components/
  ui/                          ← Generische Bausteine
    HmButton.vue
    HmBadge.vue
    HmInput.vue
    HmFormGroup.vue
    HmIconButton.vue
    HmEmptyState.vue
    HmToolbar.vue
    HmSplitView.vue
    HmKeyValue.vue
    HmSectionHeader.vue
    index.ts                   ← Barrel Export
  domain/                      ← Business-Context-aware
    HmStateBadge.vue           ← nutzt HmBadge
    HmSourceBadge.vue
    HmPriorityBadge.vue
    ...
```

- **Prefix `Hm`** (für Hivemind) — konsistent mit bestehendem `vue-component`-Skill Empfehlung `Hv`
- Alle Styles via Design Tokens — **keine hardcoded px, Hex, rgba**
- Prop-Defaults explizit via `withDefaults`
- Alle Emits typisiert via `defineEmits<{...}>()`

---

## Implementierungsstrategie

### Phase 1 — Foundation (Tier 1 Components)

1. **HmButton erstellen** → Token-basiert, alle Varianten + Sizes
2. **HmBadge erstellen** → mit Farbmapping per `variant`
3. **HmInput erstellen** → Fokus-Ring, Error-State
4. **HmFormGroup erstellen** → Label + Slot + Error
5. **Component-Tokens erweitern** in `components.css`: `--badge-*`, `--input-*`

### Phase 2 — Migration (Views refactoren)

Pro View:
1. Lokale `.btn-*`-Klassen → `<HmButton variant="..." size="...">`
2. Lokale Badge-Klassen → `<HmBadge variant="...">`
3. Lokale Input-Styles → `<HmInput>`
4. Hardcoded Pixel → `var(--space-*)` / `var(--radius-*)`
5. Hardcoded Farben → `var(--color-*)`

**Reihenfolge nach Impact:**
1. PromptStationView (~1098 Zeilen, meiste Duplikation)
2. TriageStationView (diverse Badge-Typen)
3. SettingsView (Formulare + Buttons)
4. CommandDeckView (Badges + Action-Buttons)
5. SkillLabView (Lifecycle-Badges)
6. WikiView
7. Restliche Views + Domain-Components

### Phase 3 — Domain Components (Tier 2)

1. `HmStateBadge`, `HmSourceBadge`, `HmPriorityBadge` extrahieren
2. Domain-Components (`TaskReviewPanel`, `EpicScopingModal`, etc.) auf Tier-1-Bausteine umstellen

### Phase 4 — Layout Components (Tier 3)

1. `HmToolbar`, `HmSplitView`, `HmSectionHeader` für wiederkehrende Layout-Muster
2. Views vereinfachen durch Layout-Components

---

## Token-Ergänzungen (components.css)

Folgende Component-Tokens fehlen aktuell:

```css
:root {
  /* Badge */
  --badge-padding-x: var(--space-2);
  --badge-padding-y: 2px;
  --badge-radius: var(--radius-sm);
  --badge-font-size: var(--font-size-xs);
  --badge-font-weight: 600;
  
  /* Badge Variants */
  --badge-success-bg: rgba(60, 255, 154, 0.15);
  --badge-success-text: var(--color-success);
  --badge-warning-bg: rgba(255, 176, 32, 0.15);
  --badge-warning-text: var(--color-warning);
  --badge-danger-bg: rgba(255, 77, 109, 0.15);
  --badge-danger-text: var(--color-danger);
  --badge-info-bg: rgba(32, 227, 255, 0.15);
  --badge-info-text: var(--color-accent);
  --badge-neutral-bg: var(--color-surface-alt);
  --badge-neutral-text: var(--color-text-muted);

  /* Button Sizes */
  --button-sm-padding: var(--space-1) var(--space-2);
  --button-sm-font-size: var(--font-size-xs);
  --button-md-padding: var(--space-2) var(--space-4);
  --button-md-font-size: var(--font-size-sm);
  --button-lg-padding: var(--space-3) var(--space-6);
  --button-lg-font-size: var(--font-size-base);
  --button-radius: var(--radius-sm);

  /* Button Variants (ergänzend zu existierenden --button-primary-*) */
  --button-secondary-bg: transparent;
  --button-secondary-text: var(--color-accent);
  --button-secondary-border: var(--color-accent);
  --button-ghost-bg: transparent;
  --button-ghost-text: var(--color-text-muted);
  --button-ghost-hover-bg: var(--color-surface-alt);

  /* Input (ergänzend) */
  --input-radius: var(--radius-sm);
  --input-padding: var(--space-2) var(--space-3);
  --input-font-size: var(--font-size-sm);
  --input-error-border: var(--color-danger);
}
```

---

## Workflow: Architekt → Skills → Worker

### Kann der Architekt das automatisch?

**Ja, mit Einschränkungen.** Der aktuelle Pipeline-Flow:

```
Epic (frontend-refactoring)
  → Architekt: zerlegt in Tasks (pro View/Component)
  → Worker: implementiert Tasks (nutzt Skills)
  → Gaertner: erntet neue Skills aus abgeschlossenen Tasks
  → Kartograph: analysiert Code, schlägt Skills vor
```

**Was automatisch funktioniert:**
- Architekt kann das Epic in Tasks pro View/Component zerlegen
- Worker kann mithilfe der bestehenden `vue-component` + `design-token` Skills implementieren
- Gaertner erntet aus den abgeschlossenen Tasks neue Pattern-Skills

**Was manuell vorbereitet werden muss:**
1. **Skills aktualisieren**: `vue-component` Skill referenziert veraltete Token-Namen (`--surface-primary` statt `--color-surface`), Pfade (`src/styles/themes/` statt `src/design/themes/`) — *muss vorher korrigiert werden*
2. **Neuen Skill erstellen**: `component-extraction` — beschreibt wann ein Pattern in ein Component extrahiert wird und die Regeln dafür
3. **Neuen Skill erstellen**: `design-system-compliance` — Audit-Checkliste: keine hardcoded Werte, immer var(), Barrel-Exports, Prop-Typing
4. **Epic anlegen** mit verständlichem Scope + Definition of Done

### Skill-Lücken (zu erstellen vor Refactoring-Start)

| Skill | Inhalt |
| --- | --- |
| `component-extraction` | Wann: ≥2 Vorkommen des selben Patterns → Extrahieren. Wie: Props ableiten, Slots für Flexibilität, Barrel-Export. Testing-Strategie. |
| `design-system-compliance` | Checkliste für Design-System-konforme Components. Token-Pflicht, keine Hardcodes, `withDefaults`, `defineEmits`, Scoped Styles, Reka-UI-First. |
| `vue-component` (Update) | Token-Namen und Pfade an aktuelles Design-System anpassen (`--color-*` statt `--surface-*`, `src/design/` statt `src/styles/`) |
| `design-token` (Update) | Aktuelle Token-Struktur (Primitiven + Semantisch + Component-Tokens) nachziehen |

### Epic-Vorschlag

```json
{
  "external_id": "EPIC-FRONTEND-REFACTORING",
  "title": "Frontend Component-Architektur — Systematisches Refactoring",
  "description": "Reduktion von Custom-CSS durch Extraktion wiederverwendbarer Micro-Components (HmButton, HmBadge, HmInput, HmFormGroup). Migration aller Views auf Design-Token-basierte Shared Components.",
  "priority": "medium",
  "definition_of_done": "1) HmButton, HmBadge, HmInput, HmFormGroup existieren mit Tests. 2) Alle Views nutzen Shared Components statt lokaler Button/Badge-Styles. 3) Null hardcoded Farben/Padding in scoped Styles. 4) Component-Tokens vollständig in components.css. 5) Skills aktualisiert.",
  "tags": ["frontend", "design-system", "refactoring", "vue3"]
}
```

---

## Metriken für Erfolg

| KPI | Ist | Soll |
| --- | --- | --- |
| Files mit eigener `.btn-*` Definition | 11+ | 0 |
| Hardcoded `border-radius` | ~100 | 0 |
| Hardcoded `padding` in px | 69 | 0 |
| Hex/rgba-Farben ohne Token | ~80 | 0 |
| UI-Components in `components/ui/` | 8 | ~18 |
| Durchschn. Scoped-CSS-Zeilen pro View | ~200 | <80 |

## Aktueller Stand (Scan: 2026-03-07)

> Automatisch generiert durch `scripts/kartograph_scan.py`

### Metriken

| KPI | Wert | Ziel |
| --- | --- | --- |
| Vue-Dateien total | 42 | — |
| UI Components (`components/ui/`) | 8 | ~18 |
| Domain Components (`components/domain/`) | 18 | ~10 |
| Views | 13 | — |
| Hardcoded Hex-Farben in Styles | 71 | **0** |
| Hardcoded rgba()-Werte in Styles | 43 | **0** |
| Hardcoded `padding`/`margin` in px | 95 | **0** |
| Hardcoded `border-radius` in px | 91 | **0** |
| Token-Referenzen `var(--)` (gesamt) | 3049 | ↑ maximieren |
| Files mit eigener `.btn-*` Definition | 19 | **0** |
| Files mit eigener `.badge-*` Definition | 5 | **0** |

### UI Components (8)

HivemindCard, HivemindDropdown, HivemindModal, McpStatusIndicator, QueueBadge, SlaCountdown, ToastContainer, TokenRadar

### Domain Components (18)

ActorBadge, AiProviderConfigPanel, AiReviewPanel, DeadLetterList, DecisionRequestDialog, EpicScopingModal, FederationSettings, GamificationBar, GovernanceConfigPanel, KpiCard, McpBridgeConfigPanel, NexusGrid3D, NotificationTray, ProjectCreateDialog, ProjectIntegrationsPanel, RequirementCaptureModal, Spotlight, TaskReviewPanel

### Files mit `.btn-*` Definitionen

  - `components/domain/AiProviderConfigPanel.vue`
  - `components/domain/AiReviewPanel.vue`
  - `components/domain/DecisionRequestDialog.vue`
  - `components/domain/EpicScopingModal.vue`
  - `components/domain/FederationSettings.vue`
  - `components/domain/GovernanceConfigPanel.vue`
  - `components/domain/McpBridgeConfigPanel.vue`
  - `components/domain/ProjectCreateDialog.vue`
  - `components/domain/ProjectIntegrationsPanel.vue`
  - `components/domain/RequirementCaptureModal.vue`
  - `components/domain/TaskReviewPanel.vue`
  - `views/CommandDeck/CommandDeckView.vue`
  - `views/KartographBootstrap/KartographBootstrapView.vue`
  - `views/NotificationTray/NotificationTrayView.vue`
  - `views/PromptStation/PromptStationView.vue`
  - `views/Settings/SettingsView.vue`
  - `views/SkillLab/SkillLabView.vue`
  - `views/Triage/TriageStationView.vue`
  - `views/Wiki/WikiView.vue`

### Files mit `.badge-*` Definitionen

  - `components/domain/ProjectIntegrationsPanel.vue`
  - `components/ui/QueueBadge.vue`
  - `views/Achievements/AchievementsView.vue`
  - `views/CommandDeck/CommandDeckView.vue`
  - `views/Triage/TriageStationView.vue`

### Top-Verletzungen pro Datei

| Datei | Hex-Farben | rgba() | Padding px | Radius px |
| --- | --- | --- | --- | --- |
| `views/Triage/TriageStationView.vue` | 3 | 10 | 15 | 16 |
| `views/CommandDeck/CommandDeckView.vue` | 2 | 1 | 17 | 16 |
| `views/SkillLab/SkillLabView.vue` | 0 | 7 | 3 | 12 |
| `views/KartographBootstrap/KartographBootstrapView.vue` | 11 | 2 | 2 | 4 |
| `views/PromptStation/PromptStationView.vue` | 10 | 0 | 7 | 2 |
| `components/domain/AiProviderConfigPanel.vue` | 6 | 0 | 5 | 6 |
| `components/domain/DecisionRequestDialog.vue` | 0 | 4 | 5 | 7 |
| `components/domain/TaskReviewPanel.vue` | 7 | 2 | 3 | 3 |
| `components/ui/SlaCountdown.vue` | 10 | 0 | 1 | 2 |
| `components/domain/NotificationTray.vue` | 0 | 1 | 5 | 4 |
| `components/ui/QueueBadge.vue` | 4 | 4 | 1 | 1 |
| `views/NotificationTray/NotificationTrayView.vue` | 0 | 0 | 6 | 4 |
| `components/domain/AiReviewPanel.vue` | 8 | 0 | 1 | 0 |
| `views/Settings/SettingsView.vue` | 3 | 0 | 4 | 2 |
| `views/NexusGrid/NexusGridView.vue` | 3 | 2 | 2 | 0 |

