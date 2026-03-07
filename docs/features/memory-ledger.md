# Memory Ledger — Agent-Gedächtnis & Infinite Context

← [Skills](./skills.md) | [Agent Skills](./agent-skills.md) | [Index](../../masterplan.md)

AI-Agenten haben endliche Kontextfenster. Ein Kartograph der ein großes Repository erkundet, oder ein Stratege der komplexe Plandokumente analysiert, stößt unweigerlich an diese Grenze — spätestens über mehrere Sessions hinweg. Das Memory Ledger löst dieses Problem: **Agenten können Arbeitsgedächtnis strukturiert in der DB persistieren, kompaktieren und verlustfrei fortsetzen**.

> Analogie: Ein Forscher der nicht alles im Kopf behalten kann, schreibt in sein Laborbuch. Regelmäßig fasst er Seiten zusammen und überträgt Schlüsselerkenntnisse auf Karteikarten. Das Laborbuch wird nie vernichtet — bei Zweifeln kann er zurückblättern.

---

## Das Problem

```text
Session 1:  Agent erkundet 30 Dateien → Kontextfenster voll
Session 2:  Neuer Kontext → Agent hat ALLES vergessen
            → Wo war ich? Was hatte ich schon verstanden?
            → Welche Hypothesen hatte ich? Welche Fragen waren offen?
```

**Bestehende Hivemind-Mechanismen (Outputs):**
- Wiki-Artikel → persistieren fertiges Wissen
- Epic-Docs → persistieren Projektkontext
- Skills → persistieren Handlungsanweisungen
- Nexus Grid → trackt welche Code-Bereiche erkundet wurden

**Was fehlt (Working Memory):**
- Zwischenbeobachtungen die noch nicht reif für einen Wiki-Artikel sind
- Hypothesen und offene Fragen
- Teilanalysen ("Ich habe /src/auth/ verstanden, aber /src/auth/oauth/ noch nicht")
- Entscheidungsfragmente ("JWT scheint hier der Ansatz, muss aber Session-Handling noch prüfen")
- Zusammenhänge zwischen Beobachtungen die über Sessions hinweg wachsen

---

## Lösung: Memory Ledger mit Progressive Summarization

Das Memory Ledger ist ein **append-only Arbeitsgedächtnis mit strukturierter Verdichtung**. Rohe Beobachtungen werden nie gelöscht — sie werden verdichtet und graduieren schließlich in das bestehende Wissenssystem (Wiki, Skills).

### Die vier Ebenen

```text
L0  Raw Observation     "JWT-Validierung in /src/auth/jwt.py gefunden, nutzt RS256"
     ↓ Extraktion
L1  Extracted Fact      { entity: "auth", key: "algorithm", value: "RS256", source: "/src/auth/jwt.py" }
     ↓ Verdichtung
L2  Session Summary     "Auth-Subsystem ist JWT-basiert (RS256), self-contained in /src/auth/,
                         abhängig von python-jose. OAuth-Flow noch nicht analysiert."
     ↓ Graduation
L3  Wiki / Skill        → create_wiki_article { "title": "Auth-Architektur", ... }
                         → propose_skill { "title": "Auth-Endpoint implementieren", ... }
```

| Ebene | Inhalt | Speicherort | Laden | Löschen |
| --- | --- | --- | --- | --- |
| **L0 — Raw** | Wörtliche Beobachtung des Agenten | `memory_entries` | On-demand (Similarity) | **Nie** (append-only) |
| **L1 — Facts** | Extrahierte Schlüsselfakten (strukturiert) | `memory_facts` | Immer bei Session-Resume | **Nie** (append-only) |
| **L2 — Summary** | Zusammenfassung einer Session oder Themengruppe | `memory_summaries` | Bei Session-Resume (aktuellste) | **Nie** (append-only, neue Summary ersetzt keine alte) |
| **L3 — Graduated** | Wiki-Artikel, Skill, Epic-Doc | Bestehende Tabellen | Via Bibliothekar | Bestehende Lifecycle-Regeln |

---

## Anti-Loss-Garantien — Wie wir sicherstellen dass nichts verloren geht

### Prinzip 1: Append-Only — Rohdaten werden nie gelöscht

```text
Memory Entries:     IMMUTABLE — kein UPDATE, kein DELETE
Memory Facts:       IMMUTABLE — kein UPDATE, kein DELETE
Memory Summaries:   IMMUTABLE — neue Summary ergänzt, ersetzt nicht
```

Genau wie `skill_versions` und `wiki_versions` ist das Memory Ledger ein unveränderliches Protokoll. Verdichtung erzeugt **neue** Einträge, verändert keine bestehenden.

### Prinzip 2: Fakten-Extraktion vor Verdichtung

Bevor eine Gruppe von L0-Observations zu einem L2-Summary verdichtet wird, extrahiert der Agent **atomare Fakten** (L1). Diese Fakten sind strukturiert und überleben jede Verdichtung:

```text
L0 Observations (Session 3, Kartograph):
  "In /src/auth/jwt.py: Klasse JWTValidator, nutzt python-jose, RS256"
  "In /src/auth/middleware.py: FastAPI Dependency, prüft Authorization-Header"
  "In /src/auth/oauth.py: OAuth2 Flow vorhanden aber auskommentiert (TODO-Kommentar)"
  "In /src/config/auth.py: JWT_SECRET aus Env-Var, Token-Expiry 1h"

     ↓ Fakten-Extraktion (L1)

  { entity: "auth/jwt",       key: "class",      value: "JWTValidator" }
  { entity: "auth/jwt",       key: "library",    value: "python-jose" }
  { entity: "auth/jwt",       key: "algorithm",  value: "RS256" }
  { entity: "auth/middleware", key: "pattern",    value: "FastAPI Depends() Middleware" }
  { entity: "auth/oauth",     key: "status",     value: "auskommentiert, TODO" }
  { entity: "auth/config",    key: "secret_src", value: "ENV:JWT_SECRET" }
  { entity: "auth/config",    key: "expiry",     value: "1h" }

     ↓ Verdichtung (L2)

  "Auth-Subsystem: JWT-basiert (RS256, python-jose), FastAPI-Middleware-Pattern.
   OAuth2 existiert aber deaktiviert (TODO). Config via Env-Vars (JWT_SECRET, 1h Expiry).
   Offene Frage: Warum OAuth deaktiviert? Refresh-Token-Handling fehlt komplett."
```

**Schlüssel-Erkenntnis:** Auch wenn die L2-Summary Details weglässt (z.B. Klassenname `JWTValidator`), sind alle diskreten Fakten in L1 erhalten und per Search abrufbar.

### Prinzip 3: Coverage-Tracking — Jede Summary weiß was sie abdeckt

```text
L2 Summary "auth-session-3":
  source_entry_ids: [entry-1, entry-2, entry-3, entry-4]   ← welche L0-Entries
  source_fact_ids:  [fact-1, fact-2, ..., fact-7]           ← welche L1-Facts
  source_count: 4 entries, 7 facts                          ← Integrity-Check
  open_questions: ["Warum OAuth deaktiviert?", "Refresh-Token?"]
```

Ein Agent kann jederzeit prüfen: **"Welche meiner Beobachtungen sind noch nicht von einer Summary abgedeckt?"** — unbedeckte Entries werden beim nächsten Resume prominent angezeigt.

### Prinzip 4: Integrity-Check bei Session-Resume

```text
Session-Resume Protocol:
  1. Lade aktuellste L2-Summaries für diesen Scope
  2. Lade alle L1-Facts (kompakt, strukturiert — wenig Tokens)
  3. Prüfe: Gibt es L0-Entries OHNE zugehörige Summary? → Warnung
  4. Prüfe: Gibt es offene Fragen in Summaries? → In den Prompt aufnehmen
  5. Lade relevante L0-Entries nur on-demand (Similarity-Search wenn Agent tiefer einsteigen will)
```

### Prinzip 5: Graduation — Reifes Wissen verlässt das Ledger

Wenn eine L2-Summary stabil genug ist (mehrfach bestätigt, keine offenen Fragen mehr), soll der Agent sie **graduieren**:

- Kartograph → `create_wiki_article` (L3)
- Gaertner → `propose_skill` (L3)
- Stratege → Wiki-Artikel oder Epic-Proposal (L3)

Graduierte Einträge werden in der Summary als `graduated: true` markiert. Sie werden nicht mehr beim Resume geladen (das Wiki/Skill-System übernimmt). Die L0/L1-Daten bleiben als Audit-Trail bestehen.

---

## Wer nutzt das Memory Ledger?

**Jeder Agent** kann das Memory Ledger nutzen — es ist ein **Cross-Cutting System Skill**. Aber die Intensität der Nutzung variiert:

| Agent | Nutzungsintensität | Typische Memory-Inhalte |
| --- | --- | --- |
| **Kartograph** | ★★★★★ Kern-Feature | Code-Beobachtungen, Architektur-Hypothesen, unerkundete Bereiche, Cross-Referenzen |
| **Stratege** | ★★★★☆ Hoch | Plan-Analyse-Fragmente, Epic-Kandidaten-Notizen, Dependency-Hypothesen, Priorisierungs-Überlegungen |
| **Architekt** | ★★★☆☆ Mittel | Dekompositions-Notizen, Boundary-Überlegungen, Skill-Matching-Beobachtungen |
| **Worker** | ★★☆☆☆ Niedrig–Mittel | Nur bei komplexen Multi-Session-Tasks: Lösungsansätze, Debugging-Erkenntnisse, Blocker-Analyse |
| **Gaertner** | ★★★☆☆ Mittel | Pattern-Beobachtungen über mehrere Tasks, Skill-Gap-Hypothesen, Composition-Ideen, **Skill-Candidate-Harvesting** |
| **Triage** | ★☆☆☆☆ Niedrig | Routing-Entscheidungsmuster, wiederkehrende Event-Typen |

### Skill-Candidate-Tagging — Cross-Agent Skill-Pipeline {#skill-candidate-tagging}

Jeder Agent kann Pattern-Beobachtungen als potentielle Skills markieren indem er den reservierten Tag **`skill-candidate`** verwendet:

```text
hivemind-save_memory {
  "scope": "project", "scope_id": "uuid",
  "content": "Repo nutzt überall Repository-Pattern: Service-Layer + Depends(). Könnte ein Skill werden.",
  "tags": ["pattern", "skill-candidate", "fastapi"]
}
```

**Das `skill-candidate`-Tag ist ein reserviertes Signal-Tag.** Es hat eine besondere Bedeutung im System:

| Aspekt | Beschreibung |
| --- | --- |
| **Wer taggt** | Jeder Agent — Kartograph, Stratege, Architekt, Worker, Gaertner |
| **Wer konsumiert** | Der Gaertner (primär) + der Kartograph (direkt via `propose_skill`) |
| **Wann konsumiert** | Gaertner sucht bei jeder Destillations-Session nach `skill-candidate`-Entries |
| **Was danach passiert** | Gaertner erstellt `propose_skill` oder `propose_skill_change`, taggt Original als `skill-candidate-processed` |
| **Qualitätsanspruch** | Niedrig — ein `skill-candidate` ist ein Hinweis, kein fertiges Proposal |

**Typische Skill-Candidate-Inhalte pro Agent:**

| Agent | Typischer Skill-Candidate | Beispiel |
| --- | --- | --- |
| **Kartograph** | Codebase-weite Coding-Patterns | "Überall Repository-Pattern + Service-Layer" |
| **Stratege** | Wiederkehrende Planungs-Patterns | "Jedes Frontend-Epic braucht Design-Token-Setup als ersten Task" |
| **Architekt** | Dekompositions-Patterns | "API-Epics immer: Schema → Endpoint → Tests → Integration" |
| **Worker** | Implementierungs-Tricks | "Bei OAuth: Token-Refresh muss vor Request-Retry stehen — immer" |
| **Gaertner** | Skill-Gaps (agiert auch als Consumer) | "Kein Skill für Alembic-Rollbacks — häufiger Bedarf" |

**Lifecycle eines Skill-Candidates:**

```text
1. Agent entdeckt Pattern → save_memory mit tag "skill-candidate"
2. Gaertner-Session → search_memories { tags: ["skill-candidate"] }
3. Gaertner bewertet: Ausreichend Kontext? Wiederverwendbar?
   3a. Ja → propose_skill + save_memory { tags: ["skill-candidate-processed"] }
   3b. Nein → Offene Frage in Memory: "Mehr Detail nötig zu [pattern]"
   3c. Bereits existierender Skill → propose_skill_change
4. Alternativ: Kartograph formalisiert direkt (nur für Codebase-weite Patterns)
```

> → Gaertner-Workflow B: [Gaertner — Skill-Candidate-Harvesting](../agents/gaertner.md)
> → Memory Skill: [Agent Skills — Skill-Candidate-Tagging](./agent-skills.md#memory-skill)

### Kartograph — Der Hauptnutzer

Das Memory Ledger ist der Kern der "Infinite Context"-Fähigkeit des Kartographen:

```text
Session 1 (Bootstrap):
  → Agent erkundet /src/ Top-Level
  → Schreibt 15 L0-Entries, extrahiert 40 L1-Facts
  → Am Session-Ende: Kompaktiert zu 3 L2-Summaries
  → Erstellt erste Wiki-Artikel (L3) für klar verstandene Bereiche

Session 2 (Vertiefung):
  → Resume: Lädt 3 L2-Summaries + 40 L1-Facts (~800 Tokens)
  → Agent weiß: "/src/auth/ verstanden, /src/api/ grob, /src/workers/ noch gar nicht"
  → Erkundet /src/workers/, schreibt neue L0-Entries
  → Am Session-Ende: Neue Summaries + Graduation der Auth-Summary zu Wiki

Session 5 (Deep Dive):
  → Resume: 5 Summaries + 120 Facts + 3 offene Fragen
  → Agent geht gezielt offene Fragen an
  → Bei Bedarf: Similarity-Search in L0-Entries für Details aus Session 1

Session 10:
  → Die meisten Summaries sind graduiert (→ Wiki)
  → Nur noch 2 aktive Summaries mit offenen Fragen
  → Memory-Footprint im Prompt: ~400 Tokens (Summaries) + ~600 Tokens (Facts)
  → Agent hat effektiv den vollen Überblick aus 10 Sessions — in ~1000 Tokens
```

### Stratege — Strategische Langzeitplanung

```text
Session 1:
  → Analysiert Masterplan Abschnitte 1-3
  → Memory: "Phase 1-3 klar, Abhängigkeiten zwischen DB und RBAC erkannt"
  → Memory Facts: { "phase_1.dependency": "postgres", "phase_2.blocks": "phase_3" }

Session 2:
  → Resume: Weiß was analysiert ist → geht zu Abschnitt 4-6
  → Erkennt Widerspruch: Phase 5 referenziert Feature aus Phase 3 anders
  → Memory: "Potentieller Widerspruch Phase 3 vs 5 bei Guard-Enforcement"
  → Open Question logged

Session 3:
  → Resume: Sieht offene Frage → klärt Widerspruch zuerst
  → Graduiert: Vollständige Epic-Landschaft als Wiki-Artikel
```

---

## MCP-Tools

### Write-Tools (alle Agenten)

```text
hivemind-save_memory {
  "scope": "project|epic|task|global",
  "scope_id": "uuid",                    -- project/epic/task ID (NULL bei global)
  "content": "...",                        -- L0: Freiform-Beobachtung (Markdown)
  "tags": ["auth", "architecture"]         -- Für Similarity + Filterung
}
-- Erstellt L0 memory_entry
-- Trigger: Automatische L1-Faktenextraktion (async, Backend oder Agent)

hivemind-extract_facts {
  "entry_ids": ["uuid", "uuid"],           -- Welche L0-Entries
  "facts": [
    { "entity": "auth/jwt", "key": "algorithm", "value": "RS256" },
    { "entity": "auth/jwt", "key": "library", "value": "python-jose" }
  ]
}
-- Agent extrahiert selbst Fakten aus L0-Entries → L1
-- Alternativ: Backend extrahiert automatisch (Phase 5+ mit LLM)

hivemind-compact_memories {
  "entry_ids": ["uuid", "uuid", "..."],    -- Welche L0-Entries zusammenfassen
  "summary": "...",                         -- L2: Verdichtete Zusammenfassung
  "open_questions": ["...", "..."],         -- Offene Fragen aus der Analyse
  "graduated": false                        -- true wenn Summary reif für Wiki/Skill ist
}
-- Erstellt L2 memory_summary, verlinkt source_entry_ids
-- Entries bleiben unverändert (append-only)

hivemind-graduate_memory {
  "summary_id": "uuid",                    -- Welche L2-Summary
  "target": "wiki|skill|doc",              -- Wohin graduiert werden soll
  "target_id": "uuid"                      -- ID des erstellten Wiki/Skill/Doc (nach Create)
}
-- Markiert Summary als graduated, verlinkt mit Ziel-Entität
-- Summary wird bei zukünftigen Resumes nicht mehr geladen
```

### Read-Tools (alle Agenten)

```text
hivemind-get_memory_context {
  "scope": "project|epic|task|global",
  "scope_id": "uuid",
  "max_tokens": 2000                       -- Token-Budget für Memory-Kontext
}
-- Returns: L2-Summaries (neueste zuerst) + L1-Facts + Integrity-Warnings
-- Respektiert Token-Budget: Summaries zuerst, dann Facts, dann L0 on-demand

hivemind-search_memories {
  "query": "authentication JWT",
  "scope": "project|epic|global",
  "scope_id": "uuid",
  "level": "L0|L1|L2|all"                 -- Welche Ebene durchsuchen
}
-- Similarity-Search über Memory Entries (nutzt pgvector ab Phase 3)
-- Phase 1-2: Volltextsuche (ILIKE / tsvector)

hivemind-get_uncovered_entries {
  "scope": "project|epic|task",
  "scope_id": "uuid"
}
-- Gibt L0-Entries zurück die von KEINER L2-Summary abgedeckt sind
-- Integrity-Check: "Was habe ich noch nicht verdichtet?"

hivemind-get_open_questions {
  "scope": "project|epic|global",
  "scope_id": "uuid"
}
-- Gibt alle offenen Fragen aus L2-Summaries zurück
-- Nützlich für Session-Planung: "Was muss ich noch klären?"
```

---

## Kompaktierungs-Protokoll (Compaction Protocol)

### Wann kompaktieren?

| Auslöser | Aktion |
| --- | --- |
| **Session-Ende** | Agent kompaktiert alle L0-Entries dieser Session zu einer L2-Summary |
| **Token-Budget-Druck** | Bibliothekar signalisiert: Memory-Kontext > 40% des Budgets → Agent sollte kompaktieren |
| **Thematischer Abschluss** | Agent hat einen Bereich vollständig verstanden → Summary + Graduation |
| **Manueller Trigger** | User/Admin fordert Kompaktierung an |

### Kompaktierungs-Workflow

```text
1. Agent sammelt alle unkompaktierten L0-Entries für den aktuellen Scope
2. Agent extrahiert L1-Facts (falls noch nicht geschehen):
   hivemind-extract_facts { "entry_ids": [...], "facts": [...] }
3. Agent schreibt L2-Summary:
   hivemind-compact_memories {
     "entry_ids": [...],
     "summary": "Zusammenfassung...",
     "open_questions": ["Was ist mit X?", "Y noch unklar"]
   }
4. Backend verifiziert:
   - Alle entry_ids existieren und gehören zum selben Scope
   - Coverage-Count wird in Summary gespeichert
   - Entries werden als "covered_by_summary_id" markiert (Metadata-Update, nicht Delete)
5. Nächster Resume lädt Summary statt der Einzeleinträge
```

### Verdichtungs-Qualitätskriterien

Der Agent folgt diesen Regeln beim Kompaktieren (Teil des Memory Skills):

1. **Erhaltungspflicht:** Jede konkrete Entität (Datei, Klasse, Konfiguration) muss in mindestens einem L1-Fact oder der Summary namentlich erwähnt sein
2. **Offene Fragen explizit:** Ungeklärtes wird als `open_questions` aufgelistet, NICHT stillschweigend weggelassen
3. **Beziehungen erhalten:** "A hängt von B ab" muss in Summary oder als L1-Fact bestehen bleiben
4. **Scope beibehalten:** Summary darf nicht breiter sein als ihre Quell-Entries (kein Halluzinieren)
5. **Confidence markieren:** Unsichere Erkenntnisse als "Hypothese" oder "Vermutung" kennzeichnen

---

## Integration in bestehende Hivemind-Systeme

### Bibliothekar-Integration

Der Bibliothekar lädt Memory-Kontext als **zusätzliche Prioritäts-Ebene**:

```text
Priorität 0.5: Memory-Kontext (L2-Summaries + L1-Facts) ← NEU
Priorität 1:   Task-spezifische Skills
Priorität 2:   Epic-Docs
Priorität 3:   Wiki-Artikel
```

Memory-Kontext wird **vor** Skills geladen — er ist der unmittelbare Arbeitskontext des Agenten und hat höchste Relevanz. Token-Budget-Anteil: max. 30% des Gesamtbudgets (konfigurierbar via `app_settings.memory_token_ratio`, Default: 0.3).

```text
Beispiel: Token-Budget 8000
  → Memory:  max. 2400 Tokens (30%)
  → Skills:  max. 3500 Tokens
  → Docs:    max. 1500 Tokens
  → Wiki:    verbleibend (~600 Tokens)
```

### Prompt-Pipeline-Integration

Jeder Prompt-Typ erhält einen optionalen Memory-Abschnitt:

```text
## Dein bisheriges Wissen (Memory Ledger)

### Zusammenfassung (letzte Session)
[L2-Summary, kompakt]

### Schlüsselfakten
- auth/jwt: algorithm=RS256, library=python-jose
- auth/middleware: pattern=FastAPI Depends()
- auth/oauth: status=deaktiviert (TODO)

### Offene Fragen
- ❓ Warum ist OAuth deaktiviert?
- ❓ Refresh-Token-Handling fehlt komplett

### ⚠ Nicht-verdichtete Beobachtungen (2)
[Entries die noch keine Summary haben — Integrity-Warnung]
```

### Nexus-Grid-Integration

Memory Entries über Code-Bereiche aktualisieren automatisch den Fog-of-War:

```text
save_memory { scope: "project", content: "Analysiert /src/auth/jwt.py..." }
  → Backend extrahiert Dateipfade aus Content
  → code_nodes WHERE path LIKE '/src/auth/%': explored_at = now() (wenn neuer)
  → Nexus Grid zeigt: Bereich kartiert
```

### Graduation-Flow

```text
L2-Summary ist stabil (keine offenen Fragen, mehrfach bestätigt)
  ↓
Agent: "Diese Erkenntnis ist reif für Wiki/Skill"
  ↓
Kartograph: hivemind-create_wiki_article { ... }
Gaertner:   hivemind-propose_skill { ... }
Stratege:   hivemind-propose_epic { ... }
  ↓
hivemind-graduate_memory { "summary_id": "...", "target": "wiki", "target_id": "..." }
  ↓
Summary markiert als graduated → wird bei Resume nicht mehr geladen
Wiki/Skill übernimmt → Bibliothekar liefert es über den normalen Kanal
```

---

## Datenmodell

> **Kanonisches Schema:** Das autoritäre Schema steht in [data-model.md](../architecture/data-model.md). Die folgenden SQL-Snippets sind vereinfachte Auszüge zur Illustration.

```sql
-- L0: Rohe Beobachtungen (append-only, NIEMALS UPDATE/DELETE)
CREATE TABLE memory_entries (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id        UUID NOT NULL REFERENCES users(id),
  agent_role      TEXT NOT NULL,              -- 'kartograph', 'stratege', 'worker', etc.
  scope           TEXT NOT NULL,              -- 'global', 'project', 'epic', 'task'
  scope_id        UUID,                       -- project/epic/task ID (NULL bei global)
  session_id      UUID NOT NULL,              -- Gruppiert Entries einer Session
  content         TEXT NOT NULL,              -- Markdown — die rohe Beobachtung
  tags            TEXT[] NOT NULL DEFAULT '{}',
  embedding       vector(768),                -- pgvector (Phase 3+)
  covered_by      UUID REFERENCES memory_summaries(id), -- NULL = nicht verdichtet
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- L1: Extrahierte Fakten (append-only, NIEMALS UPDATE/DELETE)
CREATE TABLE memory_facts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_id        UUID NOT NULL REFERENCES memory_entries(id),  -- Quelle
  entity          TEXT NOT NULL,              -- z.B. "auth/jwt", "config/db"
  key             TEXT NOT NULL,              -- z.B. "algorithm", "pattern"
  value           TEXT NOT NULL,              -- z.B. "RS256", "Singleton"
  confidence      FLOAT DEFAULT 1.0,         -- 0-1: Wie sicher ist dieser Fakt?
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Index für schnelles Entity-Lookup
CREATE INDEX idx_memory_facts_entity ON memory_facts(entity);
CREATE INDEX idx_memory_facts_entry ON memory_facts(entry_id);

-- L2: Verdichtete Zusammenfassungen (append-only)
CREATE TABLE memory_summaries (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id        UUID NOT NULL REFERENCES users(id),
  agent_role      TEXT NOT NULL,
  scope           TEXT NOT NULL,
  scope_id        UUID,
  session_id      UUID,                       -- Session die diese Summary erzeugt hat
  content         TEXT NOT NULL,              -- Markdown — die verdichtete Zusammenfassung
  source_entry_ids UUID[] NOT NULL,           -- Welche L0-Entries abgedeckt
  source_fact_ids  UUID[] NOT NULL DEFAULT '{}', -- Welche L1-Facts referenziert
  source_count    INT NOT NULL,               -- Integrity: Anzahl Quell-Entries
  open_questions  TEXT[] NOT NULL DEFAULT '{}', -- Noch ungeklärte Fragen
  graduated       BOOLEAN NOT NULL DEFAULT false,
  graduated_to    JSONB,                      -- { "type": "wiki", "id": "uuid" } bei Graduation
  embedding       vector(768),
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Sessions: Gruppiert L0-Entries einer Arbeitssitzung
CREATE TABLE memory_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id        UUID NOT NULL REFERENCES users(id),
  agent_role      TEXT NOT NULL,
  scope           TEXT NOT NULL,
  scope_id        UUID,
  started_at      TIMESTAMPTZ DEFAULT now(),
  ended_at        TIMESTAMPTZ,                -- NULL = aktive Session
  entry_count     INT NOT NULL DEFAULT 0,     -- Wird bei jedem save_memory inkrementiert
  compacted       BOOLEAN NOT NULL DEFAULT false  -- true wenn Session kompaktiert wurde
);
```

### Indizes

```sql
-- Scope-basiertes Laden (häufigster Query-Pfad)
CREATE INDEX idx_memory_entries_scope ON memory_entries(scope, scope_id, created_at DESC);
CREATE INDEX idx_memory_summaries_scope ON memory_summaries(scope, scope_id, graduated, created_at DESC);
CREATE INDEX idx_memory_sessions_scope ON memory_sessions(scope, scope_id, ended_at DESC);

-- Nicht-verdichtete Entries finden (Integrity-Check)
CREATE INDEX idx_memory_entries_uncovered ON memory_entries(scope, scope_id) WHERE covered_by IS NULL;

-- pgvector-Similarity-Search (Phase 3+)
CREATE INDEX idx_memory_entries_embedding ON memory_entries USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_memory_summaries_embedding ON memory_summaries USING hnsw (embedding vector_cosine_ops);
```

---

## RBAC

Memory-Daten gehören dem Actor und sind scope-gebunden:

| Permission | Wer | Beschreibung |
| --- | --- | --- |
| `save_memory` | Alle Agenten-Rollen | Eigene Memories schreiben |
| `read_own_memory` | Alle Agenten-Rollen | Eigene Memories lesen (gleicher actor_id) |
| `read_scope_memory` | developer (eigene Projekte), admin (alle) | Memories anderer Agenten im selben Scope lesen |
| `compact_memory` | Alle Agenten-Rollen | Eigene Memories kompaktieren |
| `graduate_memory` | kartograph, gaertner, stratege | Memory zu Wiki/Skill/Doc graduieren |

> **Cross-Agent-Lesbarkeit:** Ein Stratege kann die Memory-Summaries des Kartographen lesen (gleicher Scope). Das ermöglicht Wissenstransfer zwischen Agenten: Der Kartograph entdeckt, der Stratege plant basierend auf den Kartograph-Erkenntnissen — auch wenn sie noch nicht als Wiki-Artikel graduiert sind.

---

## Phasen-Einordnung

| Phase | Memory-Fähigkeit | Kompaktierung |
| --- | --- | --- |
| **Phase 1** | DB-Schema erstellt (alle Tabellen vorhanden); `save_memory` als MCP-Read/Write-Tool; Memory-Abschnitt im Prompt | **Manuell:** Agent schreibt Summary im Prompt, User speichert |
| **Phase 2** | Memory-UI im Command Deck (Session-History, Fact-Browser) | **Manuell** via Agent-Prompt |
| **Phase 3** | pgvector-Embeddings für Memory-Similarity; `search_memories` mit Semantic Search; Bibliothekar-Integration | **Semi-automatisch:** Agent + Similarity-basierte Vorschläge |
| **Phase 4** | `compact_memories`, `graduate_memory` als MCP-Write-Tools | **Agent-gesteuert** (Agent entscheidet wann) |
| **Phase 5** | Automatische Faktenextraktion (Backend-LLM); Integrity-Checks | **Assistiert:** Backend extrahiert L1, Agent kompaktiert L2 |
| **Phase 8** | Vollautonome Kompaktierung; proaktive Graduation; Cross-Agent Memory | **Autonom** |

---

## Token-Budget-Implikation

Memory-Kontext verbraucht Token-Budget. Richtwerte:

```text
L1-Facts:       ~3-5 Tokens pro Fakt (key=value)
                100 Facts ≈ 400 Tokens

L2-Summary:     ~100-300 Tokens pro Summary
                5 Summaries ≈ 800 Tokens

Open Questions: ~20 Tokens pro Frage
                5 Fragen ≈ 100 Tokens

Typischer Resume-Kontext:
  3 Summaries + 50 Facts + 3 Open Questions
  ≈ 600 + 200 + 60 = ~860 Tokens
```

Bei Token-Budget 8000 und memory_token_ratio=0.3 stehen 2400 Tokens für Memory zur Verfügung — das reicht für ca. 8 Sessions mit je 50 Facts. Danach verdichtet sich der Memory-Stack weiter (Summaries über Summaries) oder Facts graduieren zu Wiki/Skills.

### Meta-Kompaktierung (Summaries über Summaries)

Wenn sich zu viele L2-Summaries ansammeln, kann eine **Meta-Summary** erstellt werden:

```text
5 Session-Summaries (à 200 Tokens = 1000 Tokens)
  → Meta-Summary (300 Tokens) + die 5 Summaries behalten ihre source_entry_ids
  → Die Meta-Summary verweist auf die 5 Summaries als source_entry_ids
  → Beim Resume: Nur Meta-Summary laden; Drill-Down in Session-Summaries on-demand
```

Dies ist rekursiv — beliebig tiefe Verdichtung möglich, wobei die L0/L1-Daten immer erhalten bleiben.

---

## Memory Skill — Cross-Agent System Skill

Das Memory Ledger wird als System-Skill in jeden Agenten-Prompt injiziert. Siehe → [Agent Skills — Memory Skill](./agent-skills.md#memory-skill).

---

## Abgrenzung

| | Memory Ledger | Wiki | Skills | Docs |
| --- | --- | --- | --- | --- |
| **Zweck** | Arbeitsgedächtnis (intermediär) | Fertiges Wissen | Handlungsanweisung | Epic-Kontext |
| **Autor** | Jeder Agent (eigene Memories) | Kartograph + Admin | Gaertner (via Proposal) | Gaertner + Kartograph |
| **Lifecycle** | L0→L1→L2→L3 (Graduation) | Living Document | Draft→Active→Deprecated | Living Document |
| **Persistenz** | Append-only, nie gelöscht | Versioniert | Versioniert | Versioniert |
| **Token-Verbrauch** | 30% Budget (Memory-Ratio) | Niedrigste Priorität | Höchste Priorität | Mittlere Priorität |
| **Zielgruppe** | Derselbe Agent (oder Cross-Agent) | Mensch + KI | KI-Agent | Mensch + KI |
| **Reife** | Unreif → reift → graduiert | Reif | Reif | Reif |

---

## FAQ

### Wird die DB nicht riesig wenn nie gelöscht wird?

Nein — L0-Entries sind typischerweise 50-200 Wörter. 10.000 Entries ≈ 5MB Text. Das ist für PostgreSQL trivial. Embeddings (768 Floats = 3KB pro Entry) verdoppeln das auf ~35MB für 10.000 Entries — immer noch minimal. Optional: `memory_entries` Partitionierung nach `created_at` (jährlich) für Very-Large-Scale.

### Was wenn der Agent schlecht kompaktiert?

1. Die Rohdaten sind nie weg → man kann immer zurückblättern
2. L1-Facts sind strukturiert und überleben schlechte Summaries
3. Integrity-Check (`get_uncovered_entries`) zeigt vergessene Entries
4. Im schlimmsten Fall: Neue Summary über dieselben Entries erstellen (die alte bleibt bestehen)

### Wie unterscheidet sich das von einfachem Chat-History-Logging?

Chat-History ist unstrukturiert und nicht verdichtbar. Das Memory Ledger hat:
- **Strukturierte Fakten** (entity/key/value) — durchsuchbar und aggregierbar
- **Explizite Verdichtung** — bewusste Zusammenfassung mit Qualitätskriterien
- **Integrity-Tracking** — nichts fällt durch die Ritzen
- **Graduation** — reifes Wissen fließt ins permanente Wissenssystem
- **Scope-Bindung** — Memories gehören zu einem Kontext (Projekt, Epic, Task)

### Kann ein Agent die Memories eines anderen Agenten lesen?

Ja, über `read_scope_memory`. Typischer Use-Case: Stratege liest Kartograph-Summaries um Planungsentscheidungen auf Erkenntnissen zu basieren die noch nicht als Wiki graduiert sind. Das Memory Ledger ist damit auch ein Cross-Agent-Kommunikationskanal für halbfertiges Wissen.
