---
title: "Cytoscape Nexus Grid: Heatmap + SSE + Performance"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "cytoscape", "sse"]
skill_type: "domain"
confidence: 0.9
source_epics: ["EPIC-PHASE-5", "EPIC-PHASE-7"]
guards:
  - title: "Frontend Typecheck"
    command: "cd frontend && npm run typecheck"
  - title: "Frontend Build"
    command: "cd frontend && npm run build"
---

## Skill: Cytoscape Nexus Grid

### Rolle
Du implementierst oder erweiterst den Nexus Grid in Vue 3 mit Cytoscape. Schwerpunkt:
- Heatmap-Layer fuer Bugs
- Live-Refresh via SSE
- performante Node-Updates mit `cy.batch()`

### Konsolidierung
Dieser Skill ersetzt:
- `seed/skills/cytoscape-graph.md`
- `seed/skills/nexus-grid-bug-heatmap-layer.md`

### Wann verwenden
Nutze diesen Skill, wenn mindestens eine der folgenden Aufgaben ansteht:
- Nexus Grid Rendering oder Interaktion auf Cytoscape anpassen
- Bug-Heatmap (Node-Groesse/Farbe) implementieren oder korrigieren
- Hover- oder Detail-Daten fuer Bug Reports erweitern
- SSE Events (`bug_aggregated`) in die Grid-Aktualisierung integrieren
- Performance-Budget im Grid absichern

### Verbindliche Standards
- Graph-Engine: Cytoscape ist verpflichtend.
- Massenupdates: Node-Styles immer innerhalb `cy.batch(...)` setzen.
- Farbgebung: Nur Design-Tokens verwenden (`--color-text-muted`, `--color-warning`, `--color-danger`, etc.).
- Heatmap-Toggle: Muss ohne Seiten-Reload funktionieren.
- Lazy Data: Bug-Daten nur laden, wenn Heatmap aktiv ist.
- Hover-Panel (Heatmap aktiv): muss `count`, `last_seen`, `stack_trace_hash`-Preview anzeigen.
- SSE: `bug_aggregated` abonnieren und Updates debounced anwenden.
- Cleanup: `EventSource.close()` und `cy.destroy()` in `onBeforeUnmount`.

### Datenquellen
- `GET /api/nexus/graph` fuer Nodes und Edges.
- `GET /api/nexus/bug-counts` fuer aggregierte Bug-Daten pro Node inklusive Details.
- `GET /api/events` (SSE), Event-Typ `bug_aggregated`.

### Heatmap-Regeln
- Radius linear skaliert zwischen konfigurierbaren Grenzen:
  - `VITE_BUG_HEATMAP_MIN_RADIUS`
  - `VITE_BUG_HEATMAP_MAX_RADIUS`
  - `VITE_BUG_HEATMAP_MAX_BUGS`
- Farbverlauf: neutral -> warning -> danger.
- Interpolation mathematisch korrekt:
  - `lerp(a, b, t) = a + (b - a) * t`
- Fallbacks fuer Token-Werte erlauben, falls CSS-Variable leer ist.

### SSE-Update-Strategie
- Nicht bei jedem Event sofort komplett neu rendern.
- Debounce (z. B. 200-500 ms) fuer Burst-Events verwenden.
- Wenn `node_id` im Event vorhanden und nicht im aktuellen Graph ist: Event ignorieren.
- Bei Netzwerkfehlern reconnecten (Backoff oder fixer Retry-Delay).

### Performance-Pattern
- Keine Full-Reinit der Cytoscape-Instanz bei reinem Style-Update.
- `cy.batch()` fuer alle Node-Style-Aenderungen verwenden:
  - width/height
  - background-color
  - opacity
- Layout nur bei strukturellen Aenderungen (Nodes/Edges), nicht bei jedem Heatmap-Tick.

### UI/UX-Mindestanforderungen
- Toolbar-Toggle fuer Heatmap mit aktivem visuellen Zustand.
- Hover-Panel neben Cursor/Node, begrenzt auf Container-Rand.
- Click auf Node oeffnet Detail-Panel.
- Click auf Graph-Hintergrund entfernt Auswahl.

### Review-Checkliste (DoD)
- [ ] Toggle aktiviert/deaktiviert Layer ohne Reload.
- [ ] Node-Groesse skaliert korrekt und ist konfigurierbar.
- [ ] Node-Farbe laeuft neutral -> orange/warning -> rot/danger via Design-Tokens.
- [ ] Hover-Panel zeigt `count`, `last_seen`, `stack_trace_hash`-Preview.
- [ ] SSE-Live-Update reagiert auf neue `bug_aggregated`-Events.
- [ ] Node-Updates erfolgen in `cy.batch()`.

### Empfohlene Verifikation
1. `cd frontend && npm run typecheck`
2. `cd frontend && npm run build`
3. Manuell:
   - Heatmap togglen
   - Hover pruefen
   - SSE Event triggern und Live-Update beobachten
