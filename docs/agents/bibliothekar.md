# Bibliothekar — Context Assembly

← [Agenten-Übersicht](./overview.md) | [Index](../../masterplan.md)

Der Bibliothekar assembled den relevanten Kontext für einen Task. Er verhindert Context-Bloat durch Progressive Disclosure: der Worker sieht nur was er braucht.

**Zwei Entwicklungsstufen — gleiches Konzept, unterschiedliche Ausführung:**

---

## Phase 1–2: Bibliothekar als Prompt (Wizard of Oz)

Hivemind generiert einen **Bibliothekar-Prompt**. Der User führt ihn im AI-Client aus. Der AI-Client entscheidet manuell welche Skills und Docs relevant sind.

```
## Rolle: Bibliothekar

Dein Auftrag: Kontext für TASK-88 assemblieren.

Verfügbare aktive Skills:
- [skill-uuid-1] FastAPI Endpoint erstellen — backend, python
- [skill-uuid-2] Datenbankmigrationen — backend, alembic
- [skill-uuid-3] PR-Review Checkliste — allgemein

Verfügbare Docs für EPIC-12:
- [doc-uuid-1] EPIC-12 Architektur — Systemüberblick

Aufgabe von TASK-88: [task.description]

Wähle die 1–3 relevantesten Skills. Erkläre kurz warum.
Baue danach den Worker-Prompt mit diesen Inhalten.
```

Der AI-Client wählt aus, begründet, und gibt den fertigen Worker-Prompt aus. **Kein Backend-Code nötig.**

---

## Phase 3+: Bibliothekar als Backend-Service (automatisiert)

Ab Phase 3 (Ollama verfügbar) übernimmt der Bibliothekar als echte Backend-Komponente:

1. Task-Entität laden (inkl. Context Boundary falls gesetzt)
2. pgvector-Similarity-Suche: Task-Embedding vs. aktive Skills
3. Skills ranken nach Similarity + Confidence + `service_scope`-Match
4. **Context Boundary prüfen:** Falls gesetzt, nur `allowed_skills` und `allowed_docs` laden — Similarity-Ranking gilt innerhalb dieser Whitelist. Kein Context Boundary = alle passenden Skills und Docs.
5. Docs laden wenn in `context_boundary.allowed_docs` enthalten (oder keine Boundary gesetzt)
6. **Wiki-Artikel via Similarity laden — Wiki ignoriert Context Boundary.** Wiki-Artikel sind globales Hintergrundwissen ohne Projekt-Scope; sie werden immer per Similarity-Suche geladen, unabhängig von Boundary-Einschränkungen.
7. Kontext-Package zusammenstellen bis `max_token_budget` — Wiki-Artikel werden zuletzt hinzugefügt und als erstes gestrichen wenn Budget erschöpft
8. Token-Count pro Element zurückgeben (→ Token Radar im UI)

### Lade-Prioritäten

```
Priorität 1: Task-spezifische Skills      (höchste Relevanz)
Priorität 2: Epic-Docs                    (projekt-spezifischer Kontext)
Priorität 3: Wiki-Artikel                 (globales Hintergrundwissen)
```

### Rückgabe-Schema (Phase 3+)

```json
{
  "task": { "...": "..." },
  "context": [
    { "type": "skill", "id": "uuid", "title": "...", "content": "...", "tokens": 420 },
    { "type": "doc",   "id": "uuid", "title": "...", "content": "...", "tokens": 210 }
  ],
  "total_tokens": 630,
  "token_budget": 8000,
  "skills_omitted": 3
}
```

---

## Token-Budget

| Konfiguration | Wert |
| --- | --- |
| Standardwert | 8000 Tokens (`HIVEMIND_TOKEN_BUDGET`) |
| Pro Task überschreibbar | via Context Boundary `max_token_budget` |
| Phase 1–2 | Richtwert für den AI-Client im Prompt, nicht technisch erzwungen |

> **Budget-Sizing-Richtwerte:** Ein typischer Skill verbraucht ~400 Tokens, ein Epic-Doc ~200, ein Wiki-Artikel ~300. Bei Skill Composition (3 Ebenen Stacking) kann ein assemblierter Skill ~600 Tokens belegen. Realistisches Minimum für einen Task mit 2 Skills + 1 Doc + 1 Wiki: **~1300 Tokens Kontext**. Der Default von 8000 Tokens lässt Spielraum für 4-6 Skills — bei komplexen Tasks mit vielen Abhängigkeiten kann das Budget knapp werden. **Empfehlung:** Budget pro AI-Provider adaptiv setzen (Claude 200K Context → höheres Budget sinnvoll, GPT-4o 128K → Default ausreichend). Konfigurations-Erweiterung für Phase 8: `HIVEMIND_TOKEN_BUDGET_PROVIDER_OVERRIDE` mit Provider-spezifischen Werten.

---

## Kartograph-Ausnahme

Für den Kartographen gilt `context_boundary_filter: false`. Der Bibliothekar liefert **alles was angefragt wird** — keine Context-Boundary-Einschränkung, keine Similarity-Filterung, kein Token-Budget-Cutoff (nur manuelle Token-Budget-Hinweise im Prompt). Der Kartograph braucht vollständigen Lesezugriff auf alle Projekte für seine Repo-Analyse.

---

## Embedding-Modell (Phase 3+)

- **Default:** Ollama mit `nomic-embed-text` — kein API-Key nötig
- **Alternative:** OpenAI `text-embedding-3-small` via `HIVEMIND_EMBEDDING_PROVIDER=openai`
- **Abstraktion:** Provider-Switch mit kontrollierter Embedding-Schema-Migration (`vector(768)`/`vector(1536)`) und anschließender Neuberechnung
- **Threshold:** Cosine-Similarity >= 0.85 für Auto-Routing; konfigurierbar via `HIVEMIND_ROUTING_THRESHOLD`

---

## Embedding-Berechnung — Trigger

Embeddings werden **asynchron** berechnet:

| Event | Aktion |
| --- | --- |
| Epic erstellt / Beschreibung geändert | `epics.embedding` (neu-)berechnen |
| Skill gemergt oder Change akzeptiert | `skills.embedding` (neu-)berechnen |
| Wiki-Artikel erstellt / aktualisiert | `wiki_articles.embedding` (neu-)berechnen |
| Doc erstellt / aktualisiert | `docs.embedding` (neu-)berechnen |
| Code-Node erstellt | `code_nodes.embedding` (neu-)berechnen |

**Mechanismus:** Background-Task im FastAPI-Prozess (Phase 3–7). Der mutating Endpoint queued die Embedding-Berechnung; sie läuft **nach** dem Response asynchron. Fehlgeschlagene Berechnungen werden geloggt und beim nächsten relevanten Write erneut versucht. Ab Phase 8: dedizierter Background-Job-Queue.

---

## Docs ohne Epic (Entwurfs-Docs)

Docs mit `epic_id = NULL` werden wie Wiki-Artikel behandelt:

- Per Similarity-Suche geladen (kein Epic-Filter möglich)
- Priorität 3 (nach Epic-Docs, gleichrangig mit Wiki-Artikeln)
- Ignorieren die Context Boundary
- Werden als erstes gestrichen wenn das Token-Budget erschöpft ist
