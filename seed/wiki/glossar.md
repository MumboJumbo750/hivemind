---
slug: "glossar"
title: "Glossar — Hivemind-Domänenbegriffe"
tags: ["glossar", "begriffe", "referenz"]
linked_epics: []
---

# Glossar — Hivemind-Domänenbegriffe

| Begriff | Beschreibung |
| --- | --- |
| **BYOAI** | Bring Your Own AI — User wählt seinen AI-Client frei |
| **Context Boundary** | Vom Architekten gesetzte Einschränkung welche Skills/Docs ein Worker sehen darf |
| **Conductor** | Orchestrator-Service (Phase 8) der Agenten autonom dispatcht |
| **Decision Request** | Blocker bei dem ein Task nicht weiterkommt — eskaliert an Owner/Admin |
| **Epic** | Großes Arbeitspaket, wird in Tasks zerlegt. States: incoming → scoped → in_progress → done |
| **Federation** | Peer-to-Peer-Verbindung zwischen Hivemind-Instanzen |
| **Fog of War** | Kartograph-Prinzip: maximale Berechtigung, aber muss aktiv erkunden |
| **Governance Level** | manual / assisted / auto — steuert Autonomiegrad pro Entscheidungstyp |
| **Guard** | Ausführbarer Check (z.B. Linter, Tests) der vor Review bestehen muss |
| **Memory Ledger** | Agent-Gedächtnis über Sessions hinweg (L1=Fakten, L2=Summaries) |
| **MCP** | Model Context Protocol — Standard für AI-Tool-Integration |
| **Nexus Grid** | Code-Graph-Visualisierung mit Fog-of-War und Bug-Heatmap |
| **Node** | Eine Hivemind-Instanz (Sovereign Node) |
| **Outbox Pattern** | Zuverlässige Event-Weitergabe über DB-Tabelle + Consumer |
| **Progressive Disclosure** | Nur task-relevanten Kontext laden, kein Context-Bloat |
| **Prompt Station** | Zentrale UI-Komponente: zeigt nächsten Agenten + generierten Prompt |
| **Review-Gate** | Pflicht-Review vor dem Abschluss jedes Tasks |
| **Skill** | Versioniertes Instruktionsdokument für AI-Agenten (Markdown + Frontmatter) |
| **Sovereign Node** | Eigenständige Hivemind-Instanz eines Entwicklers |
| **Task** | Atomares Arbeitspaket innerhalb eines Epics |
| **Token Budget** | Maximale Tokenzahl die der Bibliothekar für einen Prompt-Kontext nutzen darf |
| **Triage** | Routing-Instanz für eingehende Events und Proposals |
| **Wiki** | Globale, projektübergreifende Wissensbasis |
