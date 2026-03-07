# Repo Health Report — Wiki-Template

> **Verwendung:** Kopiere dieses Template als Basis für den `hivemind-create_wiki_article`-Aufruf.
> Tags: `diagnostics`, `technical-debt`
> Scan-Datum im Titel angeben: z.B. `Repo Health Report 2026-03-04`

---

## Repo Health Report — {{DATUM}}

**Scan-Kommando:** `python scripts/health_check.py --format json`
**Repo-Root:** `{{REPO_ROOT}}`
**Gesamt-Status:** {{OK | WARNINGS | ERRORS}}

---

## Übersicht: Analyzer-Ergebnisse

| Analyzer | Errors | Warnings | Infos | Status |
|----------|--------|----------|-------|--------|
| `hardcoded-css` | {{N}} | {{N}} | {{N}} | 🔴 / 🟡 / ✅ |
| `magic-numbers` | {{N}} | {{N}} | {{N}} | 🔴 / 🟡 / ✅ |
| `duplicate-code` | {{N}} | {{N}} | {{N}} | 🔴 / 🟡 / ✅ |
| `dependency-freshness` | {{N}} | {{N}} | {{N}} | 🔴 / 🟡 / ✅ |
| *(weitere Analyzer)* | | | | |
| **Gesamt** | **{{N}}** | **{{N}}** | **{{N}}** | |

> 🔴 = mind. 1 Error · 🟡 = nur Warnings · ✅ = clean

---

## Detail: Top-10 Findings pro Kategorie

### `{{ANALYZER-NAME}}` ({{N}} Errors, {{N}} Warnings)

| Datei | Zeile | Severity | Meldung |
|-------|-------|----------|---------|
| `{{FILE}}` | {{LINE}} | error | {{MESSAGE}} |
| `{{FILE}}` | {{LINE}} | warning | {{MESSAGE}} |
| *(weitere Findings …)* | | | |

*(Abschnitt pro Analyzer mit Findings wiederholen — max. Top 10 pro Kategorie)*

---

## Abgeleitete Guard-Proposals

Für jeden Analyzer mit `severity=error`-Findings wird ein Guard-Proposal generiert:

| Guard-Name | Executable | Begründung |
|------------|-----------|------------|
| `{{analyzer}}-check` | `python scripts/health_check.py --analyzers {{analyzer}} --severity error` | {{N}} Errors beim initialen Scan |

> Diese Guards wurden via `hivemind-propose_guard` eingetragen.

---

## Empfehlungen: Cleanup-Themen

### Sofortmaßnahmen (severity=error, viele Findings)

- **{{Thema}}** — {{N}} Errors in `{{analyzer}}`: {{Kurzbeschreibung des Problems}}
  - Vorschlag: Epic `"{{Titel}}"` anlegen

### Mittelfristig (severity=warning, >10 Findings)

- **{{Thema}}** — {{N}} Warnings in `{{analyzer}}`: {{Kurzbeschreibung}}

### Optional (severity=info)

- **{{Thema}}** — {{N}} Infos: {{Kurzbeschreibung}}

---

## Guard-Template (Copy-Paste für `hivemind-propose_guard`)

```json
{
  "tool": "hivemind-propose_guard",
  "arguments": {
    "name": "{{analyzer-name}}-check",
    "description": "Kein {{analyzer-name}}-Fehler erlaubt — abgeleitet aus Repo Health Scan vom {{DATUM}}.",
    "executable": "python scripts/health_check.py --analyzers {{analyzer-name}} --severity error",
    "exit_code_pass": 0,
    "exit_code_fail": 1
  }
}
```

---

## Epic-Proposal-Template (bei >5 Errors in einem Analyzer)

```json
{
  "tool": "hivemind-propose_epic",
  "arguments": {
    "title": "{{Analyzer-Name}}: Findings bereinigen",
    "description": "Health-Scan vom {{DATUM}} hat {{N}} Errors in `{{analyzer-name}}` gefunden. Systematisches Cleanup erforderlich.",
    "tags": ["technical-debt", "health-scan"]
  }
}
```

---

*Generiert vom Kartograph-Agent · Template: `docs/features/health-report-template.md`*
