# UI-Konzept — Design & Architektur

← [Index](../../masterplan.md)

---

## Design-Philosophie

**Sci-Fi OS meets Game HUD** — kein "Enterprise-Software", sondern ein lebendes, reagierendes System. Der User fühlt sich wie ein Commander der einen Agenten-Schwarm dirigiert.

### Drei Leitprinzipien

1. **Progressive Reveal** — Features werden erst dann aktiv nutzbar, wenn sie benötigt werden. Vorher sind nur Lock-Teaser mit klarer Unlock-Bedingung erlaubt; leere States sind lehrreich, nicht leer.
2. **Always Oriented** — User weiß immer: wo bin ich, was läuft, was ist als nächstes fällig.
3. **Game Loop** — Jede Aktion fühlt sich wie ein Spielzug an — klare Konsequenz, klares Feedback, klarer nächster Schritt.

---

## Visuelles System

### UI-Framework: Reka UI

- Frontend-Komponenten basieren auf **Reka UI Primitives** (Dialog, Dropdown, Tabs, Tooltip, Scroll Area, etc.)
- Reka UI bleibt unstyled/headless; Hivemind liefert die visuelle Schicht über eigene Tokens und Theme-Klassen
- Gemeinsame Wrapper-Komponenten liegen in `src/components/ui/` (einheitliche Accessibility + Look)

### Design Tokens (verbindlich)

Alle visuellen Werte sind token-basiert. Keine Hex-Codes, keine festen Pixelwerte direkt in Feature-Komponenten.

- Verbindlicher Detailvertrag: [Design Tokens Schema](./design-tokens.md)

| Token-Layer | Beispiel | Zweck |
| --- | --- | --- |
| Core | `--space-4`, `--radius-md`, `--font-mono` | Primitive Basiswerte |
| Semantic | `--color-bg`, `--color-surface`, `--color-text`, `--color-accent` | Bedeutung statt konkreter Farbe |
| Component | `--button-primary-bg`, `--card-border`, `--badge-warning-bg` | Stabiler Look für UI-Bausteine |

### Theme-System

- Theme-Switch erfolgt runtime via `data-theme="<theme-name>"` auf Root-Level
- Alle Themes sind dark-first in Phase 1-5; Light-Varianten sind optional ab späteren Phasen
- **Default Theme:** `space-neon`
- Pflichtfelder je Theme sind im [Design Tokens Schema](./design-tokens.md) definiert

| Theme | Charakter | Einsatz |
| --- | --- | --- |
| `space-neon` | Tiefdunkle Flächen + Cyan/Magenta Neonakzente | Standard |
| `industrial-amber` | Dunkelgrau + Amber/Orange Warnästhetik | Operations-lastige Teams |
| `operator-mono` | Reduzierte Monochrom-Palette + dezente Cyan-Akzente | Fokus/Low-Distraction |

### Space-Neon (Default) — Semantic Tokens

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

### Typographie

```text
Headings:  "Space Grotesk" oder "Orbitron"  (sci-fi, klar lesbar)
Body:      "Inter" oder "DM Sans"           (neutral, gut lesbar)
Mono:      "JetBrains Mono"                 (Code, IDs, Prompts)
```

### Ikonografie & Symbole

```text
◈  Hivemind-Symbol / aktiver Agent / Peer-Node-Indikator
◌  wartend / inaktiv
●  kartiert / erledigt
░  Fog of War / unbekannt
▶  Aktion starten
✓  Erfolg
⚠  Warnung / SLA-Risiko
◎  Architekt-Agent
◬  Kartograph-Agent (Scout)
⊕  Gaertner-Agent
⚔  Skill / Arsenal-Item
```

---

## Layout — Drei-Zonen-Prinzip

```text
┌──────────────────────────────────────────────────────────────────┐
│  SYSTEM BAR  [◈ alex-hivemind]  [PROJECT ▾]  [SOLO]  [● MCP]   │
├────────────┬─────────────────────────────────┬───────────────────┤
│            │                                 │                   │
│  NAV       │   MAIN CANVAS                   │  CONTEXT PANEL    │
│  SIDEBAR   │                                 │                   │
│            │   Wechselt je nach aktiver       │  Prompt Station   │
│  ◈ STATION │   Ansicht:                      │  — oder —         │
│  ○ QUESTS  │   · Command Deck (Standard)     │  Detail-Ansicht   │
│  ○ TRIAGE  │   · Nexus Grid / Weltkarte      │  des selektierten │
│  ○ ARSENAL │   · Triage Station              │  Elements         │
│  ○ WIKI    │   · Arsenal / Skill Lab         │                   │
│  ○ KARTE   │   · Wiki                        │                   │
│  ○ GILDE   │   · Gilde / Federation          │                   │
│  ○ CONFIG  │   · Settings                    │                   │
│            │                                 │                   │
├────────────┴─────────────────────────────────┴───────────────────┤
│  STATUS BAR  [MCP ✓]  [3 Tasks aktiv]  [⚠ SLA: EPIC-12 in 4h]  │
│              [EXP: ████████░░░░░░░░░░░ Lvl. 5 Commander]         │
└──────────────────────────────────────────────────────────────────┘
```

### System Bar — Phase F Erweiterung

Ab Phase F zeigt die System Bar den Node-Namen und Gilde-Status:

```text
Phase 1–2 (Solo):
  [◈ alex-hivemind]  [PROJECT ▾]  [SOLO]  [● MCP]

Phase F (Game Mode):
  [◈ alex-hivemind]  [PROJECT ▾]  [◈ GILDE: 2/3 ▾]  [● MCP]
                                        └─ Hover/Click:
                                           ● ben-hivemind   online
                                           ● clara-hivemind online
                                           ○ old-node       offline

Phase F (Pro Mode):
  [◈ alex-hivemind]  [PROJECT ▾]  [◈ FEDERATION: 2/3 ▾]  [● MCP]
```

### Zonen-Verhalten

| Zone | Beschreibung | Kollabierbar |
| --- | --- | --- |
| System Bar | Immer sichtbar — Node-Name, Projekt, MCP-Status | Nein |
| Nav Sidebar | Navigation + Notification-Badges | Ja (Icon-Only-Modus) |
| Main Canvas | Primäre Ansicht — wechselt je nach Selektion | Nein |
| Context Panel | Prompt Station oder Detail-Ansicht | Ja (mehr Canvas-Fläche) |
| Status Bar | Immer sichtbar — System-Health, kritische SLAs | Nein |

### Focus Mode (ab Phase 2 empfohlen)

Für kognitiv schwere Aufgaben kann die UI in einen Fokusmodus wechseln:

- **Prompt-Fokus:** blendet Nav Sidebar und Status Bar temporär aus, wenn der User Volltext-Prompts liest oder editiert.
- **Map-Fokus:** maximiert Nexus Grid (2D/3D) auf die volle Canvas-Breite; Context Panel öffnet nur on-demand.
- **Sicherheitsprinzip:** Kritische Alarme bleiben sichtbar als kompakter Overlay-Strip (SLA rot, Decision Requests, Escalations).

### Nav Sidebar — Progressive Reveal (Phasen-Rollout)

Nav-Items erscheinen nicht alle auf einmal. Jede Phase schaltet neue Bereiche frei. Items die noch nicht verfügbar sind, erscheinen **ausgegraut mit Lock-Icon** und einem Tooltip ("Verfügbar ab Phase X").

**Klarstellung Progressive Reveal:** "Reveal" bedeutet in Hivemind nicht "unsichtbar bis Phase X", sondern "nicht interaktiv bis Phase X". Lock-Items sind als Roadmap-Hinweis erlaubt, solange sie (1) eine klare Freischaltbedingung zeigen und (2) keinen Dead-End-Click erzeugen.

Die Sidebar zeigt je nach Tone-Einstellung (siehe **i18n Tone-System** weiter unten) unterschiedliche Labels — die Icons und die Struktur bleiben identisch.

```text
Phase 1 (frischer Install):
  ◈ STATION / PROMPT STATION   ← aktiv
  ○ QUESTS / COMMAND DECK      ← gesperrt (🔒 Phase 2)
  ○ TRIAGE                     ← gesperrt (🔒 Phase 3)
  ○ ARSENAL / SKILL LAB        ← gesperrt (🔒 Phase 4)
  ○ WIKI                       ← gesperrt (🔒 Phase 5)
  ○ WELTKARTE / NEXUS GRID     ← gesperrt (🔒 Phase 5)
  ○ GILDE / FEDERATION         ← gesperrt (🔒 Phase F)
  ○ CONFIG / SETTINGS          ← aktiv

Phase 2:
  ◈ STATION / PROMPT STATION   ← aktiv
  ● QUESTS / COMMAND DECK      ← freigeschaltet (neu!)
  ○ TRIAGE                     ← gesperrt (🔒 Phase 3)
  ○ ARSENAL / SKILL LAB        ← gesperrt (🔒 Phase 4)
  ○ WIKI                       ← gesperrt (🔒 Phase 5)
  ○ WELTKARTE / NEXUS GRID     ← gesperrt (🔒 Phase 5)
  ○ GILDE / FEDERATION         ← gesperrt (🔒 Phase F)
  ○ CONFIG / SETTINGS          ← aktiv

Phase F (nach Phase 2):
  ... alle Phase-2-Items +
  ● GILDE / FEDERATION         ← freigeschaltet!

Phase 5:
  ◈ STATION   ● QUESTS   ● TRIAGE   ● ARSENAL   ● WIKI
  ● WELTKARTE   ● GILDE (wenn Phase F)   ● CONFIG
```

**Leer-State-Verhalten:** Wenn ein Item freigeschaltet wurde aber noch keine Daten vorhanden sind, zeigt die View einen **lehrreichen Leer-State** (kein leeres Panel):

| View | 🎮 Game Mode | 💼 Pro Mode | Aktion |
| --- | --- | --- | --- |
| Prompt Station | "Kein Projekt aktiv. Der Schwarm wartet." | "Kein Projekt aktiv. Starte mit dem Kartographen." | [NEUES PROJEKT ANLEGEN] |
| Command Deck | "Noch keine Quests. Starte dein erstes Epic." | "Noch keine Epics. Lege dein erstes Epic an." | [+ EPIC ANLEGEN] |
| Triage Station | "Keine offenen Items — System läuft sauber." | "Keine offenen Items — System läuft sauber." | — |
| Arsenal / Skill Lab | "Noch keine Skills. Schließe deine erste Quest ab." | "Noch keine Skills. Schließe deinen ersten Task ab." | — |
| Wiki | "Gildenwissen leer. Starte den Scout." | "Noch keine Artikel. Starte den Kartographen." | Prompt Station öffnen |
| Nexus Grid | "░░░ Weltkarte leer — kein Land in Sicht." | "Noch nicht kartiert. ░░░ Fog of War total." | Prompt Station öffnen |
| Gilde | "Noch keine Peers — du kämpfst allein." | "Keine verbundenen Nodes. Konfiguriere Federation." | [PEER HINZUFÜGEN] |

---

## Ansichten (Views)

| View | 🎮 Game Label | 💼 Pro Label | Zweck | Phase |
| --- | --- | --- | --- | --- |
| **Prompt Station** | BEFEHLSSTATION | PROMPT STATION | Agent-Queue, aktiver Prompt | 1 |
| **Command Deck** | QUESTS | COMMAND DECK | Epics + Tasks, State Machine, SLA | 2 |
| **Triage Station** | TRIAGE | TRIAGE | Unrouted Events, Proposals, Dead Letters | 3 |
| **Arsenal** | ARSENAL | SKILL LAB | Skills + Guards browsen, Proposals | 4 |
| **Wiki** | WIKI | WIKI | Wissensartikel lesen und navigieren | 5 |
| **Nexus Grid** | WELTKARTE | NEXUS GRID | Code-Graph, Fog of War, Bug-Heatmap | 5 |
| **Gilde** | GILDE | FEDERATION | Peer-Übersicht, Shared Epics, Gildenwissen | F |
| **Settings** | CONFIG | SETTINGS | MCP-Config, AI-Provider, Solo/Team, Themes | 1 |

---

## Gamification-Elemente

### Core Game Loop

Jede Aktion fühlt sich wie ein Spielzug an — klare Konsequenz, klares Feedback, klarer nächster Schritt:

```text
QUEST ERHALTEN  →  MERCENARY AUSRÜSTEN  →  QUEST STARTEN
     ↓                                          ↓
BRIEFING                                 ERGEBNIS EINREICHEN
(Prompt Station)                         (submit_result)
                                               ↓
                                    REVIEW (pass/fail)
                                               ↓
                                    ✓ QUEST ABGESCHLOSSEN
                                       (Loot: Artifact)
```

### Visuelle Feedback-Elemente (Micro-Interactions & Juice)

Ein UI fühlt sich nach "Spiel" an, wenn jede Interaktion befriedigendes, fast schon physisches Feedback gibt ("Juice").

- **SLA-Countdown:** Sichtbarer Timer der sich orange → rot färbt — Druck ohne Panik
- **Fog of War:** Das Aufdecken durch den Kartographen passiert nicht instantan, sondern als sichtbare "Scan"-Welle (Radial Reveal) über das Grid (░ → ●)
- **State-Transitions:** Task `in_progress` → `in_review` → `done` mit kurzem Pulse-Effekt; Epic `done` löst einen dezenten Glow-Effekt über der Epic-Card aus.
- **Agent-Badges:** Jeder Agent hat ein eigenes Symbol (◈ Worker, ◎ Architekt, ◬ Kartograph, ⊕ Gaertner)
- **Token Radar:** Animierter Progress-Ring der zeigt wieviel Kontext geladen ist (Loadout-Gewicht)
- **Skill Confidence Bar:** Visueller Indikator der Verlässlichkeit eines Skills im Arsenal
- **Prompt Queue Fortschritt:** "3 von 5 Agenten-Aufgaben heute erledigt" — Game-Loop-Gefühl
- **Peer-Farben im Nexus Grid:** Jeder Peer hat eine eigene Akzentfarbe für seine Discoveries
- **Discovery Session Pulse:** Aktive Kartograph-Sessions pulsieren auf der Weltkarte
- **Skill Pinning (Loadout):** Physisches "Snap"-Feedback — wenn ein Skill im Arsenal in das Loadout gezogen wird, gibt es ein sattes, visuelles Einrasten mit einem kurzen Aufleuchten des Token-Budgets.
- **Guard Checks (Sequential Reveal):** Guard-Prüfungen ploppen als sequenzielles "Aufblinken" und Abhaken (✓) pro Guard auf, um Spannung zu erzeugen.

### Progression & Rewards (Commander Rank/EXP)

Die persistente Weiterentwicklung des Users motiviert langfristig (nicht nur pro Quest):

- **Experience Points (EXP):** Jeder abgeschlossene Task bringt EXP. Besondere Tasks (z. B. gelöste Eskalationen, erfolgreich destillierte Skills) generieren Bonus-EXP.
- **Level-Ups:** Fortschritt in den "Commander Ranks" (Node-Levels) schaltet neue kosmetische UI-Themes oder Avatare frei (z.B. spezielle Farbe in der Gilden-Weltkarte).
- **Achievements/Medaillen**: Ein Trophäenschrank im Profil (z.B. "Fog Clearer" = 500 Code-Nodes erkundet, "Guild Contributor" = 10 eigene Skills von Peers übernommen). Diese sind für Peers in der Gilde sichtbar.

### Mercenary Loadout Moment

Der wichtigste Moment im Game-Loop. Bevor eine Quest startet, wechselt die Prompt Station in den **BRIEFING-State** — der Kommandant rüstet den Mercenary mit Skills aus dem Arsenal aus. Dieses Ritual (Skill auswählen → Budget prüfen → starten) erzeugt Ownership und Verantwortungsgefühl.

### Gilde als sozialer Layer (Koop-Mechaniken)

Federation ist nicht nur Infrastruktur — es ist das soziale Spiel:

- **Peers sehen was du explorierst** → Koordination ohne Meeting
- **Federated Skills teilen** → echte Wissenstransfers als Spielmoment
- **Shared Quests** → gemeinsam an einem Epic arbeiten → Erfolgserlebnis geteilt
- **Sync-Strikes (Co-op Bonus):** Wenn zwei verbundene Nodes gleichzeitig an Tasks desselben Shared Epics arbeiten, erhalten beide visuell leuchtende Avatar-Grenzen für die Session.
- **Mercenary Verleih:** Wenn eine Quest an einen Peer delegiert wird und dieser sie abschließt, erhält die vergebende Node eine spezielle "Guild Support"-Notification inklusive speziellem Loot-Icon.

---

## i18n — Tone-System: Game / Pro

Hivemind unterstützt zwei Interface-Tones die in den Settings umschaltbar sind. **Kein Feature ist versteckt** — beide Modes zeigen alle Funktionen. Primär variiert die Sprache; sekundär dürfen Dichte und Motion-Profil variieren.

### Konfiguration

```text
Settings → Tab CONFIG → Interface-Tone:
  🎮 Game Mode   (Standard — sci-fi, metaphorisch)
  💼 Pro Mode    (professionell, neutral)
```

**Technisch:** `vue-i18n` mit zwei Locale-Varianten pro Sprache (`de.game.json` / `de.pro.json`). Laufzeit-Switch ohne Reload.

### Interaction-Profil pro Tone

| Aspekt | Game Mode | Pro Mode |
| --- | --- | --- |
| Textstil | metaphorisch, motivierend | neutral, operativ |
| Informationsdichte | normal | kompakt (höhere Informationsdichte) |
| Motion | stärkeres Feedback (Pulse, Progress, Session-Highlights) | reduziert, ruhiger |
| Ziel | Orientierung + Ritualisierung | schnelle operative Entscheidungen |

Das Interaction-Profil ändert keine Daten, keine Rechte und keine Workflow-Logik — nur Darstellung und Bedienrhythmus.

### Term-Mapping

| Konzept | 🎮 Game Mode | 💼 Pro Mode |
| --- | --- | --- |
| Entwickler | Kommandant | Developer |
| Hivemind-Instanz | Base / Outpost | Node |
| Worker-Agent (AI-Client) | Mercenary | Worker |
| Task | Quest | Task |
| Epics-Übersicht | Quests | Command Deck |
| Skills gepinnt auf Task | Loadout | Pinned Skills |
| Skills + Guards browsen | Arsenal | Skill Lab |
| Federation | Gilde | Federation |
| Nexus Grid | Weltkarte | Nexus Grid / Code-Graph |
| Kartograph-Agent | Scout | Kartograph |
| Prompt Station | Befehlsstation | Prompt Station |
| Peer-Node zuweisen | Quest delegieren | Task zuweisen |
| Skill aus Peer-Node | Gildenwissen | Federated Skill |
| Federated Discovery | Karte erkunden | Code-Discovery |

### Leer-States & Notifications

Auch Leer-States und Notification-Texte wechseln den Tone:

| Moment | 🎮 Game Mode | 💼 Pro Mode |
| --- | --- | --- |
| Nexus Grid leer | "░░░ Kein Land in Sicht — starte die Exploration" | "Noch keine Code-Daten — starte den Kartographen" |
| Task startet | "Quest gestartet — Mercenary ist im Einsatz" | "Task gestartet — Worker ist aktiv" |
| Task done (Peer) | "⚔ Quest abgeschlossen! [◈ ben-hivemind]" | "Task erledigt — ben-hivemind" |
| Skill aus Peer | "Gildenwissen übernommen [von: ben-hivemind]" | "Skill übernommen [von: ben-hivemind]" |
| Discovery Session | "[◬ clara erkundet frontend/ ...]" | "[◬ clara analysiert frontend/ ...]" |
| Loadout-Screen | "MERCENARY BRIEFING" | "WORKER VORBEREITEN" |
| Quest starten | [QUEST STARTEN ▶] | [TASK STARTEN ▶] |

### Was NICHT variiert

Folgende Grundlagen bleiben in beiden Modes identisch:

- **Feature-Umfang und Rechte** (RBAC, States, Actions, Guards)
- **Informationsarchitektur** (Nav-Reihenfolge, View-Struktur, Datenmodell)
- **Technische Begriffe**: **MCP**, **Guard**, **Epic**, **SLA**
- **Kritische Labels mit hoher Eindeutigkeit**: **Wiki**, **Triage**

---

## Progressive Reveal — Onboarding

```text
Frischer Install → nur Prompt Station + Settings sichtbar:
  🎮 "Kein Projekt aktiv. Der Schwarm wartet auf Befehle."
  💼 "Kein Projekt aktiv. Starte mit dem Kartographen."
  [NEUES PROJEKT ANLEGEN]
  ↓
Nach erstem Projekt:
  → Nexus Grid erscheint (leer, Fog of War total)
  → Prompt Station zeigt den ersten Kartograph-Prompt
  ↓
Nach erstem Kartograph-Run:
  → Wiki füllt sich (erste Gildenwissen-Einträge)
  → Nexus Grid zeigt erste kartierte Nodes (Fog lichtet sich)
  → Command Deck erscheint (jetzt mit echten Daten)
  ↓
Nach Phase F:
  → Gilde/Federation freigeschaltet
  → System Bar zeigt Node-Name + Peer-Status
  → Weltkarte zeigt Peer-Entdeckungen in Farbe
  ↓
...und so weiter. Jede Phase erschließt neue UI-Bereiche.
```

---

## Markdown-Rendering-Strategie

**Library: TipTap** (Vue 3, headless, MIT-Lizenz)

TipTap wird systemweit als einzige Markdown/Rich-Text-Lösung eingesetzt — sowohl für **Read-only-Darstellung** als auch für **Editier-Modi**. Kein zweites Rendering-System daneben.

### Warum TipTap

| Kriterium | TipTap |
| --- | --- |
| Vue 3 native | ✓ `@tiptap/vue-3` |
| Headless / token-basiert stylebar | ✓ Kein CSS mitgeliefert |
| Read-only Modus | ✓ `editable: false` |
| Markdown-Import/Export | ✓ via `@tiptap/extension-markdown` |
| Code-Syntax-Highlighting | ✓ `CodeBlockLowlight` + `lowlight` |
| Tabellen | ✓ `@tiptap/extension-table` |

### TipTap-Konfiguration (Pflicht-Extensions)

```typescript
// src/components/ui/editor/tiptap-config.ts
import StarterKit from '@tiptap/starter-kit'
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight'
import Table from '@tiptap/extension-table'
import { Markdown } from 'tiptap-markdown'
import { createLowlight } from 'lowlight'
import python from 'highlight.js/lib/languages/python'
import typescript from 'highlight.js/lib/languages/typescript'
import yaml from 'highlight.js/lib/languages/yaml'

const lowlight = createLowlight()
lowlight.register({ python, typescript, yaml })

export const hivemindExtensions = [
  StarterKit.configure({ codeBlock: false }),
  CodeBlockLowlight.configure({ lowlight }),
  Table.configure({ resizable: false }),
  Markdown,
]
```

### Einsatzorte

| Kontext | Modus | Wo |
| --- | --- | --- |
| Wiki-Artikel lesen | `editable: false` | Wiki View |
| Wiki-Artikel bearbeiten (Admin) | `editable: true` | Wiki Editor Modal |
| Skill-Detail anzeigen | `editable: false` | Skill Lab Detail |
| Skill Change Proposal bearbeiten | `editable: true` | Skill Lab Editor |
| Task-Ergebnis anzeigen (Review Panel) | `editable: false` | Command Deck Review |
| Decision Records lesen | `editable: false` | Command Deck Epic-Detail |
| Volltext-Prompt lesen | `editable: false` | Prompt Station Volltext-Modal |
| Prompt anpassen (Prompt Station) | `editable: true` (Markdown) | Prompt Station Inline-Editor |

### Wrapper-Komponenten

```text
src/components/ui/editor/
  HivemindViewer.vue    ← TipTap editable:false, nur Rendering
  HivemindEditor.vue    ← TipTap editable:true, mit Toolbar
```

Beide Komponenten erhalten ihren Style ausschließlich über Design Tokens — kein hardcoded CSS. Die Toolbar von `HivemindEditor` nutzt ausschließlich Component-Tokens (`--button-ghost-bg`, `--card-border`, etc.).

---

## Mobile / Responsive

- **Desktop-First:** Haupt-Zielplattform ist Desktop-Browser (Entwickler-Workflow)
- **Tablet:** Sidebar collapsible, Context Panel als Modal
- **Kein Mobile-Fokus** in Phase 1–5
- **Mindestbedienbarkeit auf schmalen Viewports:** kritische Aktionen (Review, Decision, Escalation) müssen ohne horizontales Scrollen erreichbar bleiben
