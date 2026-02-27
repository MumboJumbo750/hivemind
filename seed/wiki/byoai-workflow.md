---
slug: "byoai-workflow"
title: "BYOAI Workflow — Bring Your Own AI"
tags: ["workflow", "byoai", "prompt-station", "phase-1"]
linked_epics: ["EPIC-PHASE-1B", "EPIC-PHASE-3"]
---

# BYOAI Workflow — Bring Your Own AI

## Prinzip

Hivemind ist in Phase 1–7 **BYOAI** — Bring Your Own AI. Das System generiert Prompts, aber der Mensch wählt seinen AI-Client frei: Claude, ChatGPT, Gemini, Ollama, oder jeden anderen.

## Ablauf

```
1. Hivemind erkennt: "TASK-88 ist ready → Worker-Prompt nötig"
2. Prompt Station zeigt: Agent-Badge + generierter Prompt
3. User kopiert Prompt → fügt in AI-Client ein
4. AI-Client antwortet (ggf. mit MCP-Tool-Calls ab Phase 3)
5. User übernimmt Ergebnis → schreibt zurück in Hivemind
6. Prompt Station zeigt nächsten Schritt
```

## Warum BYOAI?

- **Keine Vendor-Lock-in** — Claude heute, GPT morgen, Ollama lokal
- **Kosten-Kontrolle** — User zahlt nur was er nutzt
- **Datensouveränität** — Prompts bleiben lokal bis der User sie sendet
- **Iterativer Übergang** — Phase 8 kann autonome AI nutzen, muss aber nicht

## Prompt Station

Die Prompt Station ist das Herzstück des BYOAI-Workflows:
- Zeigt welcher Agent als nächstes dran ist
- Generiert den vollständigen Prompt mit relevantem Kontext
- Bietet "In Zwischenablage kopieren"-Button
- Token Radar zeigt Budget-Auslastung (ab Phase 3)

## Übergang zu Autonomie (Phase 8)

Ab Phase 8 kann Hivemind Prompts direkt an AI-APIs senden. Der BYOAI-Modus bleibt als Fallback immer verfügbar. Kein Architekturbruch.
