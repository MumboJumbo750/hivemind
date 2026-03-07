# Agent Character Production Pack

← [Agent Character Cards](./agent-character-cards.md) | [UI-Konzept](./concept.md) | [Index](../../masterplan.md)

Dieses Dokument ist der **direkte Produktions-Handoff** für Bildgenerierung und Asset-Erstellung.

Es reduziert die ausführliche Konzept-Doku auf das, was für die Produktion wirklich gebraucht wird:

- zu liefernde Assets
- Format- und Exportregeln
- Qualitätskriterien
- Freigabeprozess
- Generator-Hinweise

---

## Lieferumfang

Pro Agent werden zunächst **2 Pflichtbilder** produziert:

1. `hero`
2. `avatar`

`portrait` ist optional in Welle 2, wenn Hero und Avatar abgenommen sind.

### Agenten

- `kartograph`
- `stratege`
- `architekt`
- `worker`
- `reviewer`
- `gaertner`
- `triage`

---

## Ziel-Dateien

### Wave 1

```text
frontend/src/assets/agents/
  kartograph/hero.webp
  kartograph/avatar.webp
  stratege/hero.webp
  stratege/avatar.webp
  architekt/hero.webp
  architekt/avatar.webp
  worker/hero.webp
  worker/avatar.webp
  reviewer/hero.webp
  reviewer/avatar.webp
  gaertner/hero.webp
  gaertner/avatar.webp
  triage/hero.webp
  triage/avatar.webp
```

### Wave 2

```text
frontend/src/assets/agents/<agent>/portrait.webp
```

---

## Formate

### Hero

- Format: `4:5`
- Zielgröße: `1536x1920`
- Export: `webp`
- Zusätzlicher Review-Export erlaubt: `png`

### Avatar

- Format: `1:1`
- Zielgröße: `512x512`
- App-Auslieferung später: `256x256` oder responsive heruntergerechnet
- Export: `webp`

### Portrait

- Format: `1:1`
- Zielgröße: `1024x1024`
- Export: `webp`

---

## Qualitätskriterien

Ein Asset ist nur freigabefähig, wenn:

1. das Gesicht oder zentrale Masken-/Helmzone klar lesbar ist
2. die Silhouette auch auf dunklem UI-Hintergrund funktioniert
3. die Agentenrolle ohne Text visuell plausibel erkennbar ist
4. keine Text- oder Wasserzeichen-Artefakte vorhanden sind
5. keine anatomischen Fehler sichtbar sind
6. der Stil mit den anderen Agenten konsistent ist
7. das Avatar in `64x64` noch erkennbar bleibt

---

## Abnahme-Check je Agent

### Hero

- Rolle visuell erkennbar
- Farbwelt korrekt
- Gesicht / Frontbereich sauber
- Hintergrund nicht überladen
- kein Stilbruch zur Serie

### Avatar

- Gesicht / Helm / Kernmotiv klar
- starke Form und Kontrast
- keine kleinen, unlesbaren Details
- funktioniert in Notification-Größe

---

## Produktionsreihenfolge

### Schritt 1 — Stil kalibrieren

Zuerst nur diese 3 Hero-Bilder erzeugen:

- `kartograph`
- `worker`
- `triage`

Warum:

- deckt Exploration, Ausführung und Leitstand ab
- zeigt früh, ob die Gesamtwelt trägt

### Schritt 2 — volle Hero-Serie

Nach Freigabe der Stilrichtung:

- `stratege`
- `architekt`
- `reviewer`
- `gaertner`

### Schritt 3 — Avatar-Serie

Avatare erst auf Basis der finalen Hero-Sprache erzeugen.

---

## Generator-Hinweise

### OpenAI `gpt-image-1`

Empfohlen:

- zuerst Heroes
- anschließend Avatare
- keine zu offenen Prompts
- immer globalen Stilblock + Negativblock anhängen

### Midjourney

Empfohlen:

- Serienkonsistenz priorisieren
- wenig Chaos
- dieselbe Prompt-Struktur über alle Agenten
- Hero und Avatar getrennt iterieren

### SDXL / lokaler Stack

Empfohlen:

- fester Seed je Agent
- gleiche Basiseinstellungen
- gleiche Upstream-Checkpoint-/Lora-Strategie

---

## Freigabeprozess

Pro Agent:

1. `hero` Rohfassung
2. Design-Review
3. Korrekturschleife
4. `hero` final
5. `avatar` auf Hero-Basis
6. Avatar-Review in kleiner Größe
7. finaler Export

---

## Übergabepaket an Produktion

Für die Bildproduktion sollten folgende Files gemeinsam übergeben werden:

- `docs/ui/agent-character-cards.md`
- `docs/ui/agent-character-production-pack.md`
- `docs/ui/agent-character-prompt-pack.json`
- `frontend/src/assets/agents/README.md`

---

## Kurzfazit

Für schnelle Produktion reicht:

- zuerst Hero + Avatar
- zuerst 3 Stil-Anker-Agenten
- dann volle Serie
- strenge Abnahme auf Lesbarkeit und Serienkonsistenz
