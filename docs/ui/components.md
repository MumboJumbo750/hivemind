# Komponentarchitektur

← [UI-Konzept](./concept.md) | [Index](../../masterplan.md)

Verbindliche Struktur für alle Vue-3-Komponenten. Ziel: keine Redundanz, keine überlangen Dateien, klare Zuständigkeiten.

---

## Vier Schichten

```text
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: Views          src/views/<view>/                      │
│  Spezifisch für genau eine View. Nicht wiederverwendet.         │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Domain         src/components/domain/                 │
│  Business-aware. Kennt Hivemind-Konzepte. In mehreren Views.    │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: UI Primitives  src/components/ui/                     │
│  Reka UI wrappers + TipTap. Kein Domain-Wissen. Pure Rendering. │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: Design         src/design/                            │
│  Tokens, Themes, CSS-Variablen. Kein Vue.                       │
└─────────────────────────────────────────────────────────────────┘
```

**Regel:** Höhere Schichten dürfen niedrigere importieren — nie umgekehrt. Eine View importiert Domain- und UI-Komponenten. Eine Domain-Komponente importiert nur UI-Primitives. Ein UI-Primitive kennt keine Domain-Konzepte.

**Dateigrößen-Grenze:** Komponenten über ~200 Zeilen werden aufgeteilt. Ausnahme: TipTap-Konfigurationen.

---

## Layer 1 — Design

Bereits in [design-tokens.md](./design-tokens.md) spezifiziert.

```text
src/design/
  tokens.css              Core-Tokens (space, radius, font, shadow, duration)
  semantic.css            Semantic-Tokens (Fallback / Default)
  components.css          Component-Tokens
  themes/
    space-neon.css
    industrial-amber.css
    operator-mono.css
```

---

## Layer 2 — UI Primitives

Reka UI-Wrappers und TipTap-Instanzen. **Kennen keine Hivemind-Konzepte** (kein "Epic", "Skill", "Guard" etc.). Empfangen Props und emittieren Events. Styled ausschließlich via Design Tokens.

```text
src/components/ui/
  HivemindCard.vue        Generische Card-Shell (slots: header, body, actions)
  HivemindViewer.vue      TipTap editable:false — Markdown read-only
  HivemindEditor.vue      TipTap editable:true  — Markdown WYSIWYG + Toolbar
  HivemindModal.vue       Reka Dialog-Wrapper (Backdrop, Größen-Slots)
  HivemindDropdown.vue    Reka Dropdown/Select-Wrapper
  HivemindTabs.vue        Reka Tabs-Wrapper (Tab-Header + Slot pro Tab)
  HivemindSearch.vue      Suchfeld mit debounce-Emit (kein Query-Handling)
  HivemindBadge.vue       Generischer Badge/Chip (variant prop: info|warning|danger|success|muted)
  HivemindProgress.vue    Generischer Progress-Ring oder -Bar (value, max, animated)
  HivemindDiff.vue        Side-by-Side Diff-Darstellung (oldText, newText props)
  HivemindTimestamp.vue   Relative oder absolute Zeit (value: ISO-String, mode: relative|absolute)
  HivemindButton.vue      Reka Button-Wrapper (variant: primary|ghost|danger)
  editor/
    tiptap-config.ts      Pflicht-Extensions (StarterKit, CodeBlockLowlight, Table, Markdown)
```

---

## Layer 3 — Domain Components

Kennen Hivemind-Konzepte. Empfangen typisierte Domain-Objekte als Props. In **mehreren Views** eingesetzt — das ist ihr Daseinszweck.

```text
src/components/domain/
  StateBadge.vue          Task/Epic-State als farbigen Badge
                          Props: state (incoming|scoped|ready|in_progress|in_review|done|
                                        blocked|escalated|qa_failed|cancelled)
                          Nutzt: HivemindBadge

  LifecycleBadge.vue      Skill/Guard-Lifecycle als Badge
                          Props: lifecycle (draft|pending_merge|active|rejected|deprecated)
                          Nutzt: HivemindBadge

  AgentBadge.vue          Agent-Symbol + Name
                          Props: agent (kartograph|architekt|worker|gaertner|triage|bibliothekar)
                          Symbole: ◬ Kartograph, ◎ Architekt, ◆ Worker, ⊕ Gaertner, ⊘ Triage, ⊙ Bibliothekar
                          (siehe concept.md Ikonografie-Sektion)

  SlaTimer.vue            SLA-Countdown mit Farb-Transition (amber → rot)
                          Props: deadline (ISO-String), compact (Boolean)
                          Nutzt: HivemindTimestamp, HivemindBadge

  TokenBudget.vue         Token-Auslastung als Ring oder Bar
                          Props: used (Number), max (Number), animated (Boolean)
                          Nutzt: HivemindProgress

  ConfidenceBar.vue       Skill-Confidence als horizontale Bar
                          Props: value (0–1)
                          Nutzt: HivemindProgress

  GuardList.vue           Liste von Guards mit Status-Icons
                          Props: guards (Guard[]), mode (definition|result)
                          mode=definition → zeigt Scope + Typ + Command (Skill Lab)
                          mode=result     → zeigt Status (passed|failed|skipped) + Output (Review Panel)
                          Nutzt: HivemindBadge

  ProposalCard.vue        Proposal-Card mit Diff + Merge/Reject-Aktionen
                          Props: proposal (SkillProposal|GuardProposal|SkillChange|GuardChange),
                                 type (skill_proposal|guard_proposal|skill_change|guard_change)
                          Emits: merge, reject
                          Nutzt: HivemindCard, HivemindDiff, HivemindBadge

  CompositionChain.vue    Extends-Kette als Pill-Reihe (A → B → C)
                          Props: chain (Skill[]) — von global nach spezifisch
                          Nutzt: HivemindBadge

  FilterBar.vue           Horizontale Tab/Chip-Leiste mit optionalen Counts
                          Props: tabs (Array<{key, label, count?}>), modelValue
                          Nutzt: HivemindTabs
```

### Reuse-Matrix

| Komponente | Prompt Station | Command Deck | Triage | Skill Lab | Wiki | Settings | Status Bar |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `HivemindViewer` | ✓ | ✓ | — | ✓ | ✓ | — | — |
| `HivemindEditor` | ✓ | — | — | ✓ | ✓ | — | — |
| `StateBadge` | ✓ | ✓ | ✓ | — | — | — | — |
| `LifecycleBadge` | — | — | ✓ | ✓ | — | — | — |
| `AgentBadge` | ✓ | ✓ | ✓ | ✓ | — | ✓ | — |
| `SlaTimer` | — | ✓ | ✓ | — | — | — | ✓ |
| `TokenBudget` | ✓ | ✓ | — | — | — | — | — |
| `ConfidenceBar` | — | — | — | ✓ | — | — | — |
| `GuardList` | ✓ | ✓ | — | ✓ | — | — | — |
| `ProposalCard` | — | — | ✓ | ✓ | — | — | — |
| `CompositionChain` | ✓ | — | — | ✓ | — | — | — |
| `FilterBar` | — | ✓ | ✓ | ✓ | ✓ | ✓ | — |

---

## Layer 4 — Views

Jede View hat ihr eigenes Unterverzeichnis. View-spezifische Subkomponenten leben dort — sie werden **nirgendwo anders importiert**.

```text
src/views/
  prompt-station/
    PromptStation.vue         Root-Komponente der View
    PromptCard.vue            Aktiver Prompt (kompakt, mit [VOLLTEXT ▤] Button)
    FulltextModal.vue         Volltext-Modal (ruft assembled:true, zeigt HivemindViewer)
    PromptQueue.vue           Geordnete Warteschlange
    PromptEditModal.vue       Inline-Editor (HivemindEditor) zum Anpassen vor dem Kopieren
    HumanActionCard.vue       "Jetzt bist DU dran"-State mit Link zur Aktion

  command-deck/
    CommandDeck.vue           Root-Komponente
    EpicCard.vue              Epic-Zeile mit SlaTimer, StateBadge, Transitions
    TaskRow.vue               Task-Zeile mit StateBadge, Aktions-Buttons
    ScopingModal.vue          Epic Scoping (Owner, SLA, Priorität, DoD-Rahmen)
    ReviewPanel.vue           Task-Review (HivemindViewer, GuardList, DoD-Checklist)
    ContextBoundaryPanel.vue  Read-only Boundary (Skills, Docs, TokenBudget)
    DecisionRecordsPanel.vue  Kollabierbare Decision-Record-Liste (HivemindViewer)
    DecisionRequestModal.vue  Modal mit Optionen + SlaTimer (Phase 6)
    DodChecklist.vue          Interaktive DoD-Checkliste (lokal in ReviewPanel genutzt)

  triage/
    TriageStation.vue         Root + Tab-Navigation (FilterBar)
    UnroutedCard.vue          [UNROUTED]-Card mit Similarity-Scores
    RestructureCard.vue       [RESTRUCTURE]-Card (HivemindViewer für Proposal-Text)
    EscalatedCard.vue         [ESCALATED]-Card mit SlaTimer + Owner-Wechsel
    DeadLetterCard.vue        [DEAD LETTER]-Card mit Requeue
    ProposalsTab.vue          Tab-Container — rendert ProposalCard (Domain) für alle Typen

  skill-lab/
    SkillLab.vue              Root + Tab (Skills | Guards)
    SkillCard.vue             Skill-Zeile (ConfidenceBar, LifecycleBadge, AgentBadge)
    SkillDetail.vue           Detail-View (CompositionChain, GuardList, HivemindViewer, VersionTimeline)
    SkillChangeEditor.vue     Change-Proposal-Formular (HivemindEditor + Diff Preview)
    GuardCard.vue             Guard-Zeile (scope-Badge, Typ-Badge)
    GuardDetail.vue           Guard-Detail (Scope-Kette, Typ, Command)
    VersionTimeline.vue       Immutable Versions-Liste (append-only)

  wiki/
    WikiView.vue              Root (Breadcrumb, Suche, Artikel-Liste)
    WikiArticle.vue           Artikel-Ansicht (HivemindViewer, Tags, Epic-Link)
    WikiEditorModal.vue       Editor-Modal für Admins (HivemindEditor)

  nexus-grid/
    NexusGrid.vue             Root (Cytoscape.js Canvas)
    NodeDetailPanel.vue       Click-Panel (Docs, Skills, Bugs, Tasks)
    LayerSwitcher.vue         Epic-Overlay Toggle
    FogOverlay.vue            Semi-transparente Maske

  settings/
    Settings.vue              Root + Tabs (FilterBar)
    SystemTab.vue             Modus, MCP-Transport, Theme
    ProjectTab.vue            Mitglieder-Liste, Rollen-Dropdowns
    AuditTab.vue              Audit-Log-Tabelle + Payload-Preview
    AiTab.vue                 API-Key, Provider, Token Budget (Phase 8)

  layout/
    SystemBar.vue             Immer sichtbar — Projekt, Modus, MCP-Status, 🔔
    NavSidebar.vue            Navigation + Progressive Reveal (lock per Phase)
    ContextPanel.vue          Rechtes Panel — Prompt Station oder Detail
    StatusBar.vue             Immer sichtbar — MCP ✓, Tasks aktiv, SLA-Warnung
    NotificationTray.vue      Aufklappbares Panel aus SystemBar (🔔)
    NotificationItem.vue      Einzelne Notification (Typ-Icon, Text, Ziel-Link)
```

---

## Entscheidungsregeln

**Wann in Domain (Layer 3) vs. direkt in View (Layer 4)?**

Kriterium: Wird die Komponente heute oder absehbar in **mehr als einer View** benötigt?

| Situation | Layer |
|---|---|
| Guard-Liste im Review Panel und im Skill Detail | → Domain: `GuardList.vue` |
| Proposal-Card in Triage und Skill Lab | → Domain: `ProposalCard.vue` |
| Epic-Scoping-Modal nur im Command Deck | → View-lokal: `command-deck/ScopingModal.vue` |
| Wiki-Editor nur im Wiki | → View-lokal: `wiki/WikiEditorModal.vue` |
| Volltext-Prompt-Modal nur in Prompt Station | → View-lokal: `prompt-station/FulltextModal.vue` |

**Wann aufteilen?**

Eine Komponente wird aufgeteilt wenn:
- sie über ~200 Zeilen wächst
- sie intern mehrere unabhängige visuelle Blöcke hat (Candidate: ReviewPanel → DodChecklist auslagern)
- sie mehrere unabhängige `emit`s hat (Candidate: ProposalCard → Merge + Reject können isoliert werden)

---

## Anbindung an den Masterplan

Dieser Komponent-Plan ist das **Bindeglied** zwischen UI-Spec und Implementierung:

- [Design Tokens](./design-tokens.md) → Layer 1
- [UI-Konzept](./concept.md) (TipTap-Strategie, Layout-Zonen) → Layer 2
- [Views](./views.md) (Mockups) → Layer 3 + 4
- [Feature-Matrix](./feature-matrix.md) (Phasen) → gibt vor wann welche Komponente gebaut wird
