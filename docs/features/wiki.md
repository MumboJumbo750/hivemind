# Wiki — Projektübergreifende Wissensbasis

← [Index](../../masterplan.md)

Das Wiki ist die **zentrale, projektübergreifende Wissensablage**. Geschrieben vom Kartographen, gelesen von Rollen mit `read_any_wiki` (developer/admin/kartograph).

---

## Abgrenzung

| | Wiki | Doc | Skill |
| --- | --- | --- | --- |
| Scope | Global, projektübergreifend | Epic-spezifisch | Task-Typ-spezifisch |
| Zielgruppe | Mensch + KI | Mensch + KI | KI-Agent |
| Inhalt | Systemarchitektur, Konventionen, Glossar, Runbooks | Epic-Kontext, Entscheidungen | Handlungsanweisung für Agenten |
| Autor | Kartograph + Admin | Gaertner + Kartograph | Gaertner (via Proposal) |
| Binding | Keine Pflicht-Verknüpfung | Epic-Pflicht | Task-Typ |
| Versionierung | Ja, append-only History | Ja | Ja, mit Task-Pinning |

---

## Typische Wiki-Inhalte

- "Unsere Authentifizierungsarchitektur" — wie Auth im Gesamtsystem funktioniert
- "Deployment-Prozess" — Schritt-für-Schritt Runbook
- "Tech Radar" — welche Technologien wir verwenden, meiden, evaluieren
- "Team-Glossar" — gemeinsame Begriffsdefinitionen
- "Epic-Abhängigkeitsmatrix" — welche Epics sich gegenseitig beeinflussen
- "Architekturentscheidungen" — langfristige ADRs

---

## Integration in den Bibliothekar

```
Priorität 1: Task-spezifische Skills      (höchste Relevanz)
Priorität 2: Epic-Docs                    (projekt-spezifischer Kontext)
Priorität 3: Wiki-Artikel                 (globales Hintergrundwissen)
```

Wiki-Artikel werden per pgvector-Similarity gegen das Task-Embedding ausgewählt — nur wenn Token-Budget es erlaubt. **Wiki-Artikel ignorieren die Context Boundary** — sie sind globales Hintergrundwissen ohne Projekt-Scope und werden immer per Similarity geladen, unabhängig von `allowed_skills`/`allowed_docs`. Die Context Boundary steuert nur Skills und Docs. Wiki-Artikel werden zuletzt hinzugefügt und als erstes aus dem Kontext gestrichen wenn das Token-Budget erschöpft ist.

---

## MCP-Tools

| Tool | Wer | Beschreibung |
| --- | --- | --- |
| `hivemind/get_wiki_article` | developer + admin + kartograph | Artikel per ID oder Slug laden |
| `hivemind/search_wiki` | developer + admin + kartograph | Semantische Suche über alle Artikel |

### Such-Semantik per Phase

| Phase | Mechanismus | Beschreibung |
| --- | --- | --- |
| Phase 1–2 | Volltextsuche (`ILIKE` / `tsvector`) | Kein Embedding vorhanden; Suche über Titel und Content |
| Phase 3+ | Hybrid (Volltext + pgvector-Similarity) | Embedding-basierte Similarity + Volltext-Fallback; Ergebnisse werden nach kombiniertem Score gerankt |

Tag-Filterung ist in allen Phasen aktiv und wird **vor** der Text-/Similarity-Suche angewendet.

### Write-Tools

| Tool | Wer | Beschreibung |
| --- | --- | --- |
| `hivemind/create_wiki_article` | Kartograph + Admin | Neuen Artikel erstellen |
| `hivemind/update_wiki_article` | Kartograph + Admin | Artikel updaten (neue Version) |
| `hivemind/link_wiki_to_epic` | Kartograph + Admin | Artikel mit Epic verknüpfen |

---

## Datenmodell

> **Kanonisches Schema:** Das autoritäre Schema steht in [data-model.md](../architecture/data-model.md). Die folgenden SQL-Snippets sind vereinfachte Auszüge zur Illustration. Bei Abweichungen gilt data-model.md.

```sql
CREATE TABLE wiki_articles (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title         TEXT NOT NULL,
  slug          TEXT NOT NULL UNIQUE,        -- URL-freundlicher Identifier
  content       TEXT NOT NULL,              -- Markdown
  tags          TEXT[] NOT NULL DEFAULT '{}',
  linked_epics  UUID[] DEFAULT '{}',
  linked_skills UUID[] DEFAULT '{}',
  author_id     UUID REFERENCES users(id),  -- NULL erlaubt für federated (origin_node_id gesetzt)
  embedding     vector(768),                -- default: nomic-embed-text; Provider-Wechsel siehe data-model.md
  version       INT NOT NULL DEFAULT 1,
  -- Federation-Spalten: origin_node_id, federation_scope — siehe data-model.md
  created_at    TIMESTAMPTZ DEFAULT now(),
  updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE wiki_versions (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id  UUID NOT NULL REFERENCES wiki_articles(id),
  version     INT NOT NULL,
  content     TEXT NOT NULL,
  changed_by  UUID NOT NULL REFERENCES users(id),
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE(article_id, version)              -- verhindert doppelte Versionen (analog zu skill_versions)
);
```
