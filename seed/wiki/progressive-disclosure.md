---
slug: "progressive-disclosure"
title: "Progressive Disclosure — Kernprinzip"
tags: ["prinzip", "architektur", "kontext"]
linked_epics: []
---

# Progressive Disclosure — Kernprinzip

## Was bedeutet Progressive Disclosure?

Progressive Disclosure ist das Designprinzip, nur die **aktuell relevanten Informationen** zu zeigen — nicht alles auf einmal. In Hivemind gilt das auf zwei Ebenen:

### 1. Kontext für AI-Agenten

Der Bibliothekar lädt nur die Skills, Docs und Wiki-Artikel die für den aktuellen Task relevant sind. Kein Context-Bloat.

```
Token-Budget: 8000 (konfigurierbar)
Priorität 0.5: Memory-Kontext     (max. 30%)
Priorität 1:   Task-Skills         (höchste Relevanz)
Priorität 2:   Epic-Docs           (Projekt-Kontext)
Priorität 3:   Wiki-Artikel        (globales Wissen)
```

### 2. UI für Menschen

Die Prompt Station zeigt immer nur den nächsten Schritt. Keine Überforderung mit 50 offenen Panels.

```
Leerer State     → "Kein Projekt aktiv"
Projekt aktiv    → Nächster Agent + Prompt
Task in_review   → Review-Panel
Epic incoming    → Scoping-Formular
```

### 3. Fog of War (Kartograph)

Der Kartograph hat maximale Berechtigung, aber muss aktiv erkunden. Was er nicht abgefragt hat, sieht er nicht. Das Nexus Grid visualisiert den Erkundungsstand.

## Warum?

- **AI:** LLMs haben endliche Context Windows. Irrelevanter Kontext verschlechtert Ergebnisse.
- **UX:** Information Overload lähmt Entscheidungen.
- **Performance:** Weniger Daten = schnellere Prompts = geringere API-Kosten.
