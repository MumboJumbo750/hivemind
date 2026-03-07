# Agent Character Cards — Art Direction, Prompt Pack und UI-Konzept

← [UI-Konzept](./concept.md) | [Components](./components.md) | [Index](../../masterplan.md)

Dieses Dokument beschreibt, wie Hivemind-Agenten als **spielartige Character Cards** inszeniert werden:

- großes Hero-Bild pro Agent
- kleines Notification-/Avatar-Bild
- klare visuelle Identität pro Rolle
- sichtbare Skills, Trigger, Schedules und Zustände

Ziel ist **bessere Orientierung**, nicht reine Dekoration.

**Produktions-Handoff:**

- `docs/ui/agent-character-production-pack.md`
- `docs/ui/agent-character-prompt-pack.json`
- `frontend/src/assets/agents/README.md`

---

## Zielbild

Jeder Agent erhält eine konsistente visuelle Repräsentation:

1. **Hero Card**  
   großformatige Charakterkarte mit Portrait, Rolle, Kernfähigkeiten, Triggern, Schedules, Governance und Status

2. **Compact Card**  
   reduzierte Karte für Listen, Stationen, Dispatch-Feeds und Auswahl-Dialoge

3. **Notification Avatar**  
   kleines, stark lesbares Icon/Portrait für Toasts, Timeline, Review-Events und In-App-Meldungen

4. **Optional Status Variants**  
   `idle`, `active`, `blocked`, `reviewing`, `warning`

---

## Warum das fachlich sinnvoll ist

Character Cards helfen nicht nur visuell, sondern operativ:

- Agentenrollen sind schneller unterscheidbar
- Notifications werden auf einen Blick verständlich
- Conductor-/Dispatch-Flows wirken greifbarer
- Governance und Trigger lassen sich direkt an der Karte erklären
- neue Nutzer verstehen das System leichter

Hivemind ist im UI bereits klar als **Game HUD / Sci-Fi OS** positioniert in `docs/ui/concept.md:1`. Character Cards passen direkt in diese Richtung.

---

## Asset-Typen

### Pflicht-Assets pro Agent

1. `hero`
   - Einsatz: Detailseite, Agent-Übersicht, leere States, Promo-Panel
   - Format: `4:5`
   - Empfehlung: `1536x1920`

2. `portrait`
   - Einsatz: Compact Card, Side Panels, Agent-Auswahl
   - Format: `1:1`
   - Empfehlung: `1024x1024`

3. `avatar`
   - Einsatz: Notifications, Timeline, Dispatch-Feed, Activity Dots
   - Format: `1:1`
   - Empfehlung: `256x256`

### Optionale Varianten

- `idle`
- `active`
- `blocked`
- `reviewing`
- `escalated`

Wenn Budget knapp ist, zuerst nur:

- `hero`
- `avatar`

---

## Stilrahmen

### Gesamtästhetik

**Genre:** sci-fi operations, tactical command, slightly game-like, premium UI concept art  
**Look:** clean, cinematic, stylized-realistic, readable silhouette, no kitsch  
**Mood:** focused, competent, role-specific, not cartoonish  
**UI-Kompatibilität:** dark-first, neon-accent capable, must work on dark blue/navy surfaces

### Gemeinsame Stilregeln für alle Agenten

- gleiche Lichtlogik
- gleiche Detailstufe
- gleiche visuelle Welt
- gleiche Bildsprache für Gesicht/Helm/Interface-Overlays
- halbfigur bis Brustportrait für Portrait/Avatar
- klare Silhouette
- keine Textblöcke im Bild
- keine Wasserzeichen
- kein überladener Hintergrund

### Negative Stilregeln

Vermeiden:

- chibi / cute
- comic übertrieben
- random fantasy ohne Sci-Fi-Operations-Bezug
- Waffenfokus
- sexuelle Inszenierung
- zu dunkle Gesichter
- kleine unlesbare Details

---

## Farb- und Formsystem pro Agent

| Agent | Kernrolle | Primärfarbe | Akzent | Formgefühl |
| --- | --- | --- | --- | --- |
| Kartograph | Explorer / Scout | Cyan | Teal | triangulär, sensorisch |
| Stratege | Planner / Tactician | Violet | Magenta | schachartig, elegant |
| Architekt | Systems Designer | Blue | White | geometrisch, konstruktiv |
| Worker | Operator / Implementer | Orange | Steel | robust, praktisch |
| Reviewer | Inspector / Judge | Red | Silver | präzise, streng |
| Gaertner | Curator / Distiller | Green | Gold | organisch, kultivierend |
| Triage | Controller / Router | Amber | Electric Blue | radial, koordinierend |

---

## Charakterprofile

### Kartograph

**Fantasy:** Scout-Analyst, Tiefensensorik, Nebel-des-Krieges-Explorer  
**Wirkung:** neugierig, präzise, entdeckend  
**UI-Schlüsselwörter:** exploration, mapping, sensor overlays, terrain scan

**Card-Metadaten**
- Skills: Repo-Erkundung, Wiki-Aufbau, Struktur-Analyse
- Trigger: Projekt-Start, Push-Event, Discovery-Follow-up
- Schedule: initial, nach größeren Strukturänderungen, on-demand

### Stratege

**Fantasy:** Taktiker, Planer, Kampagnenkommandant  
**Wirkung:** ruhig, intelligent, strategisch  
**UI-Schlüsselwörter:** campaign map, planning lines, dependency web

**Card-Metadaten**
- Skills: Requirement→Epics, Roadmap, Priorisierung
- Trigger: neue Anforderungen, Kartograph-Output, Planungsbedarf
- Schedule: vor Architekt, bei großen Scope-Änderungen

### Architekt

**Fantasy:** Systemdesigner, Bauplanmeister  
**Wirkung:** strukturiert, exakt, konstruktiv  
**UI-Schlüsselwörter:** blueprint, grid, modular systems, technical overlays

**Card-Metadaten**
- Skills: Epic-Dekomposition, Task-Schnitt, Boundaries
- Trigger: Epic `scoped`, Re-Design, Restructure
- Schedule: vor Worker-Phase

### Worker

**Fantasy:** Spezialist im Feld, Operator, Umsetzer  
**Wirkung:** fokussiert, effizient, handlungsnah  
**UI-Schlüsselwörter:** toolkit, execution, field console, practical systems

**Card-Metadaten**
- Skills: Implementierung, Guard-Ausführung, Result-Abgabe
- Trigger: Task runnable / Epic run slot frei
- Schedule: während aktiver Epic-Ausführung

### Reviewer

**Fantasy:** Auditor, Richter, Qualitätsinspektor  
**Wirkung:** scharf, sachlich, unbestechlich  
**UI-Schlüsselwörter:** scanning lens, seal, verification, inspection frame

**Card-Metadaten**
- Skills: DoD-Prüfung, Review-Empfehlung, Reject/Approve
- Trigger: Task `in_review`
- Schedule: nach Worker-Abgabe

### Gaertner

**Fantasy:** Wissensgärtner, Kurator, Destillierer  
**Wirkung:** ruhig, kultivierend, reflektierend  
**UI-Schlüsselwörter:** growth patterns, refinement, archive, cultivation

**Card-Metadaten**
- Skills: Skill-Kandidaten, Doc-Updates, Learnings
- Trigger: Task `done`, `qa_failed`, wiederkehrende Muster
- Schedule: nach Abschluss- oder Feedback-Zyklen

### Triage

**Fantasy:** Leitstand-Offizier, Dispatcher, Verkehrslenker  
**Wirkung:** aufmerksam, reaktionsschnell, priorisierend  
**UI-Schlüsselwörter:** command center, routing matrix, warning radar, queue control

**Card-Metadaten**
- Skills: Routing, Zuordnung, Eskalation, Proposal-Entscheidung
- Trigger: inbound event, proposal submitted, decision request
- Schedule: event-driven

---

## Bildprompt-System

### Globaler Stil-Prompt

Diesen Block an jeden Bildprompt anhängen:

```text
stylized realistic sci-fi character portrait, premium game character card art, dark futuristic command interface aesthetic, high readability silhouette, cinematic rim light, subtle holographic overlays, clean background composition, no text, no watermark, dark navy and neon compatible palette, polished concept art, sharp face lighting, role-specific equipment, high contrast, premium UI key art
```

### Globaler Negativ-Prompt

```text
blurry, low contrast, unreadable face, chibi, cartoon, anime exaggeration, childish, fantasy armor overload, weapon focus, text, logo, watermark, extra limbs, deformed hands, cluttered background, washed out colors, oversaturated neon mess
```

---

## Agenten-Prompts — Hero Images

### Kartograph — Hero

```text
Kartograph, explorer-analyst agent of a futuristic software hivemind, androgynous tactical scout, cyan and teal palette, triangular sensor motifs, holographic map shards floating around, scanning the unknown architecture of a digital world, calm focused expression, layered field jacket with lightweight high-tech fabric, subtle reconnaissance visor, background hints of star-map meets code topology, premium concept art, 4:5 portrait
```

### Stratege — Hero

```text
Stratege, strategic planner agent of a futuristic software hivemind, composed tactical commander, violet and magenta palette, elegant long coat with subtle geometric command patterns, holographic dependency lines and campaign-map overlays, analytical gaze, chess-like planning symbolism without literal chessboard overload, refined command deck atmosphere, premium concept art, 4:5 portrait
```

### Architekt — Hero

```text
Architekt, systems designer agent of a futuristic software hivemind, blue and white palette, blueprint holograms, modular construction motifs, precise engineer aesthetic, structured high-tech coat with hard surface detailing, calm and exact posture, digital schematic overlays, composition suggesting building complex systems from clean modules, premium concept art, 4:5 portrait
```

### Worker — Hero

```text
Worker, implementation specialist agent of a futuristic software hivemind, orange and steel palette, practical operator gear, compact tools integrated into suit, focused execution posture, field-console overlays, subtle sparks of active work, grounded competent look, not militaristic, not heavy combat, premium concept art, 4:5 portrait
```

### Reviewer — Hero

```text
Reviewer, quality inspector agent of a futuristic software hivemind, red and silver palette, precise inspection optics, thin scanning monocle or visor, judgment and verification motifs, controlled stern expression, elegant inspector uniform with high-detail trim, holographic approval and warning frames, premium concept art, 4:5 portrait
```

### Gaertner — Hero

```text
Gaertner, knowledge cultivator agent of a futuristic software hivemind, green and gold palette, organic-digital refinement motifs, archive garden symbolism rendered as elegant holographic growth patterns, calm reflective expression, curator robes mixed with technical utility, subtle seed-to-structure visual language, premium concept art, 4:5 portrait
```

### Triage — Hero

```text
Triage, command-and-routing controller agent of a futuristic software hivemind, amber and electric blue palette, command center operator, radial queue and alert overlays, highly attentive expression, dispatch console atmosphere, controlled urgency, clean officer silhouette, routing matrix visuals, premium concept art, 4:5 portrait
```

---

## Agenten-Prompts — Avatar / Notification

Diese Varianten sollen deutlich einfacher und ikonischer sein.

### Kartograph — Avatar

```text
close portrait avatar of Kartograph, futuristic scout analyst, cyan teal palette, clean face lighting, readable silhouette, subtle sensor visor, minimal holographic map motif, square composition
```

### Stratege — Avatar

```text
close portrait avatar of Stratege, strategic commander, violet magenta palette, intelligent calm expression, minimal command overlay, square composition
```

### Architekt — Avatar

```text
close portrait avatar of Architekt, systems designer, blue white palette, blueprint glow, precise technical aesthetic, square composition
```

### Worker — Avatar

```text
close portrait avatar of Worker, practical implementation specialist, orange steel palette, focused expression, compact tool motif, square composition
```

### Reviewer — Avatar

```text
close portrait avatar of Reviewer, strict quality inspector, red silver palette, scanning lens, sharp expression, square composition
```

### Gaertner — Avatar

```text
close portrait avatar of Gaertner, knowledge curator, green gold palette, calm cultivated look, subtle growth pattern motif, square composition
```

### Triage — Avatar

```text
close portrait avatar of Triage, routing controller, amber electric blue palette, alert command-center feel, minimal radial UI motif, square composition
```

---

## Prompt-Vorlage für echte Bildgeneratoren

### OpenAI / `gpt-image-1`

Struktur:

```text
[ROLE PROMPT]

Style:
[GLOBAL STYLE PROMPT]

Constraints:
- no text
- no watermark
- one character only
- highly readable face
- dark-ui compatible colors

Negative:
[GLOBAL NEGATIVE PROMPT]
```

### Midjourney

Empfehlung:

- zuerst Hero-Versionen
- danach auf Basis derselben Sprache die Avatare
- Parameter als Startpunkt:
  - `--ar 4:5` für Hero
  - `--ar 1:1` für Avatar
  - `--stylize` moderat
  - keine zu extreme Chaos-Werte

### SDXL / lokale Generatoren

Empfehlung:

- feste Seed pro Agent
- gleicher Sampler / CFG für Serienkonsistenz
- getrennte Workflow-Vorlagen für Hero und Avatar

---

## Character Card Datenmodell

Empfohlene logische Felder:

```json
{
  "agent_key": "worker",
  "display_name": "Worker",
  "tagline": "Implements runnable tasks with guard discipline",
  "role_summary": "Ausführender Agent für konkrete Task-Umsetzung",
  "skills": [
    "Implementierung",
    "Guard-Ausführung",
    "Result-Abgabe"
  ],
  "triggers": [
    "task_runnable",
    "epic_run_slot_available"
  ],
  "schedules": [
    "event_driven"
  ],
  "governance_scope": [
    "review_gate"
  ],
  "typical_inputs": [
    "task",
    "context_boundary",
    "skills",
    "guards"
  ],
  "typical_outputs": [
    "result",
    "artifacts",
    "guard_results"
  ],
  "hero_image": "/assets/agents/worker-hero.webp",
  "portrait_image": "/assets/agents/worker-portrait.webp",
  "avatar_image": "/assets/agents/worker-avatar.webp"
}
```

---

## Card-Aufbau

### Große Card

Empfohlen:

- Hero Image
- Name + Rolle
- kurzer Flavor-Text
- Skills
- Trigger
- Schedule
- Governance-Hinweis
- aktueller Status
- optional letzter Dispatch / nächste Aktion

### Kleine Card

- kleines Portrait
- Name
- Status
- 1 Zeile Rolle
- optional nächster Trigger

### Notification-Chip

- Avatar
- Agentenname
- Kurzereignis
- Severity/Status-Farbe

Beispiel:

```text
[Reviewer Avatar] Reviewer
TASK-88 rejected — Resume packet created
```

---

## Einsatzorte im UI

Empfohlene Platzierung:

- Agenten-Übersicht / Command Deck
- Epic-Run-Orchestrierung
- Prompt Station
- Triage Station
- Notification Center
- Activity Feed / Dispatch Feed
- Review Panel

---

## Asset-Ablage

Empfohlene Struktur:

```text
frontend/src/assets/agents/
  kartograph/
    hero.webp
    portrait.webp
    avatar.webp
  stratege/
    hero.webp
    portrait.webp
    avatar.webp
  architekt/
    hero.webp
    portrait.webp
    avatar.webp
  worker/
    hero.webp
    portrait.webp
    avatar.webp
  reviewer/
    hero.webp
    portrait.webp
    avatar.webp
  gaertner/
    hero.webp
    portrait.webp
    avatar.webp
  triage/
    hero.webp
    portrait.webp
    avatar.webp
```

---

## Produktionsreihenfolge

Empfohlen:

1. Art Direction finalisieren
2. Erst Hero-Bilder aller 7 Agenten erzeugen
3. Danach Avatar-Varianten erzeugen
4. Danach UI-Komponenten bauen
5. Danach Notification- und Dispatch-Integration

Nicht zuerst UI ohne Asset-Standard bauen.

---

## Fazit

Character Cards sind für Hivemind fachlich sinnvoll, weil sie:

- Rollen lesbarer machen
- Zustände schneller kommunizieren
- Dispatches emotional und visuell greifbar machen
- die Game-HUD-Richtung des Produkts stärken

Das richtige Zielbild ist:

**eine konsistente Agenten-Ästhetik mit Hero-Art, Avatar-System, klaren Card-Metadaten und starker Einbindung in Dispatch-, Notification- und Operator-Views.**
