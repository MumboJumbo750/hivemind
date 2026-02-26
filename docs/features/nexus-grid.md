# Nexus Grid — Code-Kartographie & Bug-Visualisierung

← [Index](../../masterplan.md)

Der Nexus Grid ist eine **interaktive 2D/3D-Graphvisualisierung** der Codebasis. Er verbindet drei Informationsebenen: Code-Struktur, Kartograph-Erkundungsstand (Fog of War) und Bug-Report-Dichte.

---

## Visualisierungskonzept

Der Nexus Grid unterstützt **Multi-Projekt-Ansicht** — alle Projekte einer Instanz können gleichzeitig dargestellt werden, mit Cross-Project-Kanten für Monorepo-Setups.

```text
+---------------------------------------------------------------+
|  NEXUS GRID      [Projekt: Alle ▾]   [2D] [3D] [Epic]        |
|                  [ backend  ■ ]                               |
|  [backend]       [ frontend ■ ]   [frontend]                  |
|  [src/auth/]●●●  [ ui-controls■]  [src/pages/]●              |
|       |  \                               |                    |
|  [auth/jwt]●                       [src/Button.tsx]●- - -►   |
|       |              ░░░░░░░░░░░░░       |                 |  |
|  [auth/session]●  ░░░ FOG OF WAR ░░░    ▼           [ui-controls]
|     (3 Bugs)      ░░░░░░░░░░░░░░░░░  [ui/Button.vue]●         |
|                                                               |
|  ● Kartiert  ○ Unerkundert  ░ Fog  ─── intra-project  - - cross-project |
+---------------------------------------------------------------+
```

| Symbol | Bedeutung |
| --- | --- |
| ● | Kartiert — Kartograph hat analysiert, Wiki/Docs vorhanden |
| ○ | Bekannt aber unerkundert — z.B. durch Import-Analyse sichtbar |
| ░ | Fog of War — vollständig unbekannt, noch nicht berührt |
| Farbe/Form | Projekt-Zugehörigkeit (jedes Projekt = eigene Farbe) |
| Größe | Bug-Report-Dichte (Sentry-Events) |
| `───` | Intra-Project Edge (import/call/dependency) |
| `- -►` | Cross-Project Edge (Monorepo-Abhängigkeit) |

---

## Multi-Projekt-Ansicht

### Projekt-Filter

```text
[Projekt: Alle ▾]        → zeigt alle Projekte, Cross-Project Kanten sichtbar
[Projekt: backend ▾]     → nur backend-Nodes + eingehende/ausgehende Cross-Project Kanten
[Projekt: ui-controls ▾] → nur ui-controls-Nodes + wer davon abhängt (reverse edges)
```

- **Default:** Aktives Projekt (aus System Bar)
- **"Alle":** Global View — alle Projekte im selben Graphraum
- Pro Projekt: eigene Knotenfarbe (aus Theme-Palette, zyklisch vergeben)
- Cross-Project Kanten: gestrichelt, Farbe = Quell-Projekt

### Cross-Project Edges (Monorepo)

Ein Edge von `frontend/src/Button.tsx` → `ui-controls/src/ui/Button.vue` wird als Cross-Project Edge gespeichert:

```sql
code_edges:
  project_id = frontend-project-id   -- Quell-Projekt
  source_id  = node("frontend/.../Button.tsx")
  target_id  = node("ui-controls/.../Button.vue")  -- anderes Projekt!
  edge_type  = 'import'
```

Der Kartograph erkennt Cross-Project-Imports automatisch wenn:

1. Beide Projekte im selben Nexus Grid (gleiche Instanz) existieren
2. Der Import-Pfad auf einen bekannten `code_node.path` eines anderen Projekts auflösbar ist

**Fog of War für fremde Projekte:** Wenn `ui-controls/src/ui/Button.vue` noch nicht kartiert ist (Node existiert noch nicht), legt der Kartograph automatisch einen `code_node` mit `explored_at = NULL` (Fog of War) im Ziel-Projekt an — sichtbar als `○` im Global View.

---

## Datenebenen

| Ebene | Quelle | Darstellung |
| --- | --- | --- |
| Code-Struktur | Repo-Analyse (Kartograph) | Knoten + Kanten (Imports, Abhängigkeiten) |
| Erkundungsstand | `code_nodes.explored_at` | Fog of War (dunkel = unerkundert) |
| Bug-Dichte | Sentry-Events per Datei/Modul | Knotengröße + Farbe (rot = viele Bugs) |
| Epic-Abdeckung | Task-zu-Datei-Mapping | Overlay-Layer |
| Skill-Lücken | Skill-Gap-Analyse des Kartographen | Markierung ohne zugeordnete Skills |

---

## Kartograph-Integration

```text
Kartograph analysiert src/auth/jwt.py
  → schreibt Wiki-Artikel "JWT-Implementierung"
  → Hivemind setzt code_nodes WHERE path = 'src/auth/jwt.py': explored_at = now()
  → Nexus Grid zeigt diesen Knoten als kartiert (● statt ░)
```

---

## UI-Anforderungen

- **2D-Modus:** Force-directed Graph (D3.js oder Cytoscape.js) — Standard
- **3D-Modus:** WebGL-basiert (Three.js) — für große Codebases
- **Fog-of-War-Overlay:** Semi-transparente Maske über unerkundeten Bereichen
- **Bug-Heatmap:** Knotengröße oder -farbe repräsentiert Bug-Dichte
- **Epic-Overlay:** Toggle — zeigt welche Nodes von welchem Epic abgedeckt werden
- **Click auf Node:** Öffnet Detail-Panel mit verlinkten Docs, Skills, Bugs, Tasks

---

## Rollout

| Phase | Was |
| --- | --- |
| Phase 1 | Datenmodell erstellen (`code_nodes`, `code_edges`) — keine Migrations-Arbeit später |
| Phase 3 | Kartograph schreibt Code-Nodes (wenn MCP-Reads aktiv) |
| Phase 5 | UI-Visualisierung (2D, wenn genügend Daten vorhanden) |
| Phase 7 | Bug-Heatmap (nach Sentry-Integration) |
| Phase 8 | 3D-Modus (Autonomie — dann sind Codebases groß genug) |

---

## Datenmodell

```sql
CREATE TABLE code_nodes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID NOT NULL REFERENCES projects(id),
  path        TEXT NOT NULL,              -- "src/auth/jwt.py"
  node_type   TEXT NOT NULL,             -- file|module|package|service
  label       TEXT NOT NULL,
  explored_at TIMESTAMPTZ,              -- NULL = Fog of War
  explored_by UUID REFERENCES users(id),
  embedding   vector(768),              -- default: nomic-embed-text; Provider-Wechsel siehe data-model.md
  metadata    JSONB,                     -- Sprache, LOC, Komplexität etc.
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE(project_id, path)
);

CREATE TABLE code_edges (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id), -- Quell-Projekt; target_id kann in anderem Projekt liegen
  source_id  UUID NOT NULL REFERENCES code_nodes(id),
  target_id  UUID NOT NULL REFERENCES code_nodes(id), -- cross-project möglich
  edge_type  TEXT NOT NULL,             -- import|call|dependency|extends
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(source_id, target_id, edge_type) -- ohne project_id: cross-project Edges eindeutig
);

CREATE TABLE node_bug_reports (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  node_id    UUID NOT NULL REFERENCES code_nodes(id),
  sentry_id  TEXT,
  severity   TEXT,
  count      INT NOT NULL DEFAULT 1,
  last_seen  TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE epic_node_links (
  epic_id UUID NOT NULL REFERENCES epics(id),
  node_id UUID NOT NULL REFERENCES code_nodes(id),
  PRIMARY KEY (epic_id, node_id)
);

CREATE TABLE task_node_links (
  task_id UUID NOT NULL REFERENCES tasks(id),
  node_id UUID NOT NULL REFERENCES code_nodes(id),
  PRIMARY KEY (task_id, node_id)
);
```
