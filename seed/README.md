# Hivemind Seed-Daten

Dieses Verzeichnis enthält das **Hivemind-Projekt als seinen eigenen ersten Anwendungsfall** — dateibasiert modelliert mit denselben Konzepten die das System später als DB-Entitäten verwaltet.

## Zweck

1. **Dogfooding** — Die Agent-Workflows (Kartograph, Architekt, Gärtner, Bibliothekar) werden konzeptionell durchgespielt
2. **DB-Seed** — Bei `docker compose up` in Phase 1 werden diese Dateien als initiale Daten importiert
3. **Onboarding** — Jeder neue User sieht sofort ein echtes, durchgeplantes Projekt

## Struktur

```
seed/
├── project.json          # Hivemind als Projekt-Entity
├── epics/                # Phasen → Epics (JSON)
├── tasks/                # Tasks pro Epic (JSON, in Unterordnern)
├── wiki/                 # Wiki-Artikel (Markdown + Frontmatter)
├── skills/               # Skills (Markdown + Hivemind-Frontmatter)
├── docs/                 # Epic-Docs / Architektur-Kontext (Markdown)
├── decisions/            # Decision Records (JSON)
└── code_nodes/           # Kartograph Code-Landkarte (JSON)
```

## Agenten-Mapping

- **Kartograph** hat die Wiki-Artikel, Epic-Docs und die Code-Node-Landkarte erstellt
- **Gärtner** hat die Skills destilliert  
- **Architekt** hat die Epics in Tasks zerlegt
- **Bibliothekar** hat die Verknüpfungen geprüft

## Import

```bash
# Wird in Phase 1a als CLI-Command oder Alembic Data-Migration implementiert
hivemind seed import --path ./seed/
```

Der Import ist **idempotent** (9 Schritte):

| Schritt | Quelle | Ziel-Tabelle | Dedup-Key |
| --- | --- | --- | --- |
| 1 | Hardcoded | `users` | `username = 'admin'` |
| 2 | `project.json` | `projects` | `slug` |
| 3 | `epics/*.json` | `epics` | `external_id` |
| 4 | `tasks/**/*.json` | `tasks` | `external_id` |
| 5 | `wiki/*.md` | `wiki_articles` + `wiki_versions` | `slug` |
| 6 | `skills/*.md` | `skills` + `skill_versions` | `title + project_id` |
| 7 | `docs/*.md` | `docs` | `title + epic_id` |
| 8 | `decisions/*.json` | `decision_records` | `decision + epic_id` |
| 9 | `code_nodes/*.json` | `code_nodes` + `code_edges` | `project_id + path` |

## Monorepo

Hivemind ist ein **Monorepo** — Backend, Frontend, Seed und Docs in einem Repository.
Die Code-Node-Landkarte in `code_nodes/` kartiert die gesamte Repo-Struktur mit typisierten
Nodes (model, service, router, view, component, etc.) und ihren Abhängigkeiten.

→ Vollständige Strategie: [docs/seed-strategy.md](../docs/seed-strategy.md)
