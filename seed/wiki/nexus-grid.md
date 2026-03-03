---
slug: nexus-grid
title: "Nexus Grid — Die Code-Landkarte"
tags: [nexus-grid, kartograph, visualisierung, code-graph]
linked_epics: [EPIC-PHASE-5, EPIC-PHASE-7, EPIC-PHASE-8]
---

# Nexus Grid — Die Code-Landkarte

Das Nexus Grid ist die visuelle Darstellung der Code-Struktur eines Projekts. Es zeigt **Code Nodes** (Dateien, Module, Services) und **Code Edges** (Abhängigkeiten, Imports, Aufrufe) als interaktiven Graphen.

## Fog-of-War-Prinzip

Nicht alle Nodes sind sofort sichtbar. Der **Kartograph** entdeckt aktiv — unerkundete Nodes erscheinen als dunkle Schatten (░), kartierte Nodes als leuchtende Punkte (●). Das Feld `explored_at` auf `code_nodes` markiert den Zeitpunkt der Entdeckung.

## Darstellungs-Modi

### 2D (Phase 5)
- **Cytoscape.js** mit Cola-Layout (Force-directed)
- Fog-of-War als CSS-Overlay auf unerkundeten Nodes
- Click → Detail-Panel mit Node-Metadata

### 3D (Phase 8)
- **Three.js** mit WebGL-Rendering
- Instanced Rendering für Performance (1000 Nodes @ 30 FPS)
- Fly-Through-Navigation (Orbit Controls)
- Fog-of-War als GLSL-Shader-Overlay

## Bug Heatmap (Phase 7)
Ein optionaler Layer färbt Nodes nach Bug-Häufigkeit ein. Datenquelle: `node_bug_reports`-Tabelle (Sentry-Aggregation → Code-Node-Zuordnung).

## Monorepo-Besonderheit

Da Hivemind ein **Monorepo** ist (Backend + Frontend + Seed in einem Repository), kartiert der Kartograph die gesamte Code-Landschaft in einem Graphen. Die `node_type`-Klassifikation unterscheidet:

| Node-Type | Beispiel |
| --- | --- |
| `root` | Monorepo-Wurzel |
| `directory` | `backend/`, `frontend/src/views/` |
| `model` | SQLAlchemy ORM Model |
| `service` | Business Logic Service |
| `router` | FastAPI Router |
| `mcp_tool` | MCP-Tool-Modul |
| `view` | Vue 3 View |
| `component` | Vue 3 Component |
| `composable` | Vue 3 Composable |
| `module` | Allgemeines Modul |
