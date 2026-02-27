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
└── docs/                 # Epic-Docs (Markdown)
```

## Agenten-Mapping

- **Kartograph** hat die Wiki-Artikel und Epic-Docs erstellt
- **Gärtner** hat die Skills destilliert  
- **Architekt** hat die Epics in Tasks zerlegt
- **Bibliothekar** hat die Verknüpfungen geprüft

## Import

```bash
# Wird in Phase 1a als CLI-Command oder Alembic Data-Migration implementiert
hivemind seed import --path ./seed/
```

→ Vollständige Strategie: [docs/seed-strategy.md](../docs/seed-strategy.md)
