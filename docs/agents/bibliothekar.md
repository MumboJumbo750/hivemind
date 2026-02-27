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

> **Klarstellung Phase 3 vs. Phase 8:** Ab Phase 3 ist der Bibliothekar ein Backend-Service mit pgvector-Similarity-Suche. Der generierte Prompt enthält automatisch die relevantesten Skills/Docs — kein manueller Wizard-of-Oz-Prompt mehr. **Phase 8 erweitert** den Bibliothekar um: (a) Provider-spezifische Token-Kalibrierung, (b) direkte AI-API-Anbindung (Prompt wird direkt an Claude/OpenAI gesendet statt kopiert), (c) adaptives Token-Budget per Provider. Der Bibliothekar als pgvector-basierter Kontext-Assembler existiert bereits seit Phase 3.

1. Task-Entität laden (inkl. Context Boundary falls gesetzt)
2. pgvector-Similarity-Suche: Task-Embedding vs. aktive Skills
3. Skills ranken nach Similarity + Confidence + `service_scope`-Match
4. **Context Boundary prüfen:** Falls gesetzt, nur `allowed_skills` und `allowed_docs` laden — Similarity-Ranking gilt innerhalb dieser Whitelist. Kein Context Boundary = alle passenden Skills und Docs.

> **Phase 1–3 (vor `set_context_boundary`):** Context Boundaries werden erst in Phase 4 via `set_context_boundary` gesetzt. In Phase 1–3 ist `context_boundaries` für jeden Task leer — der Bibliothekar lädt immer alle passenden Skills/Docs und nutzt den globalen `app_settings.token_budget_default` (8000). Das ist erwartetes Verhalten, nicht eine unbehandelte Lücke.
5. Docs laden wenn in `context_boundary.allowed_docs` enthalten (oder keine Boundary gesetzt)
6. **Wiki-Artikel via Similarity laden — Wiki ignoriert Context Boundary.** Wiki-Artikel sind globales Hintergrundwissen ohne Projekt-Scope; sie werden immer per Similarity-Suche geladen, unabhängig von Boundary-Einschränkungen.
7. Kontext-Package zusammenstellen bis `max_token_budget` — Wiki-Artikel werden zuletzt hinzugefügt und als erstes gestrichen wenn Budget erschöpft
8. Token-Count pro Element zurückgeben (→ Token Radar im UI)

### Lade-Prioritäten

```
Priorität 0.5: Memory-Kontext             (L2-Summaries + L1-Facts, max. 30% des Budgets)
Priorität 1:   Task-spezifische Skills     (höchste Relevanz)
Priorität 2:   Epic-Docs                  (projekt-spezifischer Kontext)
Priorität 3:   Wiki-Artikel               (globales Hintergrundwissen)
```

> **Memory-Kontext (→ [Memory Ledger](../features/memory-ledger.md)):** Wird **vor** Skills geladen — er ist der unmittelbare Arbeitskontext des Agenten. Token-Budget-Anteil: max. 30% des Gesamtbudgets (konfigurierbar via `app_settings.memory_token_ratio`, Default: 0.3). Nur geladen wenn Memory-Einträge für den aktuellen Agent-Scope existieren.

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
| Standardwert | 8000 Tokens (`app_settings.token_budget_default`) |
| Pro Task überschreibbar | via Context Boundary `max_token_budget` |
| Provider-Override (Phase 8) | Per-Agent-Rolle konfigurierbar via `ai_provider_configs`-Tabelle (→ [Agent-Provider-Routing](#agent-provider-routing)) |
| Memory-Budget-Ratio | `app_settings.memory_token_ratio` (Default: 0.3 = 30% für Memory-Kontext) |
| Phase 1–2 | Richtwert für den AI-Client im Prompt, nicht technisch erzwungen |

**Präzedenz-Reihenfolge (höchste zuerst):**

1. `context_boundaries.max_token_budget` (Task-spezifisch, vom Architekten gesetzt)
2. `ai_provider_configs.token_budget` (Per-Agent-Rolle, **erst ab Phase 8 evaluiert** — in Phase 1–7 existiert diese Stufe nicht, da kein Provider bekannt ist)
3. `app_settings.token_budget_default` (DB-persistiert, Admin-setzbar, Default: 8000)

> **Phase 1–7:** Die Budget-Kaskade hat effektiv **2 Stufen** (context_boundary → app_settings.token_budget_default). Stufe 2 (Per-Agent-Provider) wird erst ab Phase 8 evaluiert, wenn der AI-Provider über `ai_provider_configs` bekannt ist.

> **Budget-Sizing-Richtwerte:** Ein typischer Skill verbraucht ~400 Tokens, ein Epic-Doc ~200, ein Wiki-Artikel ~300. Bei Skill Composition (3 Ebenen Stacking) kann ein assemblierter Skill ~600 Tokens belegen. Realistisches Minimum für einen Task mit 2 Skills + 1 Doc + 1 Wiki: **~1300 Tokens Kontext**. Der Default von 8000 Tokens lässt Spielraum für 4-6 Skills — bei komplexen Tasks mit vielen Abhängigkeiten kann das Budget knapp werden. **Empfehlung:** Budget pro AI-Provider adaptiv setzen (Claude 200K Context → höheres Budget sinnvoll, GPT-4o 128K → Default ausreichend).

### Token-Budget — Worked Example

**Szenario:** TASK-88 "Implement JWT Refresh Token" mit Context Boundary (`max_token_budget = 6000`).

```text
Schritt 1: Effektives Budget bestimmen
  context_boundaries.max_token_budget = 6000   ← nimmt Vorrang
  (app_settings.token_budget_default = 8000 wird ignoriert)
  Effektives Budget = 6000

Schritt 2: Memory-Budget reservieren
  memory_token_ratio = 0.3 (Default)
  Memory-Budget = 6000 × 0.3 = 1800 Tokens max
  (Nur verwendet wenn Memory-Einträge existieren — sonst 0 verbraucht)

Schritt 3: Kontext assemblieren (Priorität-Reihenfolge)

  P0.5 Memory-Kontext (wenn vorhanden):
    L2-Summary "FastAPI Auth Progress"  → 280 Tokens   [geladen]
    L1-Fact "JWT_SECRET env var"        → 45 Tokens    [geladen]
    Memory-Subtotal: 325 Tokens (< 1800 Limit ✓)

  P1 Task-Skills (via Similarity-Ranking):
    "FastAPI Auth Pattern" (v3)          → 420 Tokens  [geladen]
    "JWT Patterns" (v2, federated)       → 380 Tokens  [geladen]
    "Pydantic v2 Models" (v1)            → 350 Tokens  [geladen]
    "Rate Limiting" (v1)                 → 410 Tokens  [SKIP — Budget wird knapp]
    Skills-Subtotal: 1150 Tokens

  P2 Epic-Docs:
    "EPIC-12 Auth Architektur"           → 210 Tokens  [geladen]

  P3 Wiki-Artikel:
    "Security Checkliste"                → 300 Tokens  [geladen]
    "OWASP Top 10"                       → 450 Tokens  [SKIP — Budget]

Schritt 4: Gesamtsumme
  325 (Memory) + 1150 (Skills) + 210 (Docs) + 300 (Wiki) = 1985 Tokens
  Budget verbleibend: 6000 - 1985 = 4015 Tokens für Task-Beschreibung,
  Guards, Prompt-Rahmen und Arbeitsbereich des Workers.

Ergebnis im API-Response:
  total_context_tokens: 1985
  token_budget: 6000
  skills_omitted: 1  ("Rate Limiting" — Budget knapp)
  wiki_omitted: 1    ("OWASP Top 10" — Budget knapp)
```

**Budget-Overflow — Ausschneiden-Reihenfolge:**

Wenn alle Items nicht passen, werden Inhalte in dieser Reihenfolge entfernt (niedrigste Priorität zuerst):

1. Wiki-Artikel (P3) — nach Similarity aufsteigend (least relevant first)
2. Epic-Docs (P2) — nach Similarity aufsteigend
3. Skills (P1) — nach Similarity aufsteigend (mindestens 1 Skill bleibt immer erhalten)
4. Memory L2-Summaries (P0.5) — L1-Facts bleiben immer, nur Summaries werden gekürzt

Hard-Limit: Wenn selbst nach vollständigem Ausschneiden das Budget noch überschritten wird (sehr großes `task.description`), wird `task.description` auf `max_token_budget × 0.5` gekürzt und eine `WARNING` geloggt: `budget_overflow_description_truncated`.

---

## Kartograph-Ausnahme

Für den Kartographen gilt `context_boundary_filter: false`. Der Bibliothekar liefert **alles was angefragt wird** — keine Context-Boundary-Einschränkung, keine Similarity-Filterung, kein Token-Budget-Cutoff (nur manuelle Token-Budget-Hinweise im Prompt). Der Kartograph braucht vollständigen Lesezugriff auf alle Projekte für seine Repo-Analyse.

---

## Agent-Provider-Routing (Phase 8) {#agent-provider-routing}

Ab Phase 8 kann **jede Agent-Rolle einen eigenen AI-Provider** nutzen. Das ermöglicht optimale Modell-Zuordnung — z.B. ein großes Modell für den Kartographen (braucht tiefes Reasoning) und ein schnelles Self-Hosted-Modell für Worker (braucht Speed).

### Konfigurationstabelle `ai_provider_configs`

Jeder Eintrag bindet eine Agent-Rolle an einen Provider + Modell + API-Key:

```text
┌─────────────┬───────────┬──────────────────┬────────────┬───────────────┐
│ agent_role   │ provider  │ model            │ endpoint   │ token_budget  │
├─────────────┼───────────┼──────────────────┼────────────┼───────────────┤
│ kartograph   │ google    │ gemini-2.5-pro   │ NULL       │ 200000        │
│ stratege     │ anthropic │ claude-sonnet-4  │ NULL       │ 100000        │
│ architekt    │ openai    │ gpt-4o           │ NULL       │ 128000        │
│ worker       │ ollama    │ llama3.3         │ http://…   │ 8000          │
│ gaertner     │ anthropic │ claude-sonnet-4  │ NULL       │ 100000        │
│ triage       │ ollama    │ llama3.3         │ http://…   │ 8000          │
└─────────────┴───────────┴──────────────────┴────────────┴───────────────┘
```

| Feld | Beschreibung |
| --- | --- |
| `agent_role` | `kartograph\|stratege\|architekt\|worker\|gaertner\|triage` — PK |
| `provider` | `anthropic\|openai\|google\|ollama\|custom` |
| `model` | Modell-Name beim Provider (z.B. `claude-sonnet-4`, `gpt-4o`, `gemini-2.5-pro`, `llama3.3`) |
| `endpoint` | Custom-Endpoint-URL (nur bei `ollama` und `custom` Pflicht; bei Cloud-Providern NULL → Standard-Endpoint) |
| `api_key_encrypted` | AES-256-GCM verschlüsselter API-Key (selbes System wie `ai_api_key_encrypted`; NULL bei Ollama) |
| `api_key_nonce` | Nonce für AES-GCM |
| `token_budget` | Token-Budget für diese Rolle (überschreibt `app_settings.token_budget_default`) |
| `rpm_limit` | Max Requests/Minute für diese Rolle (überschreibt `app_settings.ai_rpm_limit`) |
| `enabled` | Boolean — deaktivierte Rollen fallen auf manuellen BYOAI-Modus zurück |

### Routing-Logik im AI-Provider-Service

```text
1. Prompt-Generator erzeugt Prompt für Agent-Rolle X
2. AI-Provider-Service: Lookup ai_provider_configs WHERE agent_role = X
   2a. Gefunden + enabled → Sende an konfigurierten Provider
   2b. Nicht gefunden → Fallback auf app_settings.ai_provider (Global-Default)
   2c. Kein Global-Default → BYOAI-Modus (Prompt Station zeigt Prompt, User kopiert manuell)
3. Token-Budget: ai_provider_configs.token_budget → app_settings.token_budget_default
```

### Hybrid-Betrieb: Automatisch + Manuell gemischt

Nicht jede Rolle muss automatisiert werden. Es ist valider Betrieb wenn z.B. nur Worker und Triage automatisiert sind, während Kartograph und Stratege weiterhin manuell (BYOAI) laufen:

```text
┌─────────────┬───────────┬────────────────┐
│ Rolle        │ Modus     │ Provider       │
├─────────────┼───────────┼────────────────┤
│ kartograph   │ MANUELL   │ User wählt     │
│ stratege     │ MANUELL   │ User wählt     │
│ architekt    │ AUTO      │ OpenAI GPT-4o  │
│ worker       │ AUTO      │ Ollama lokal   │
│ gaertner     │ AUTO      │ Claude         │
│ triage       │ AUTO      │ Ollama lokal   │
└─────────────┴───────────┴────────────────┘
```

Die Prompt Station zeigt für manuelle Rollen weiterhin den kopierbaren Prompt. Für automatisierte Rollen zeigt sie den Monitoring-Modus.

### Beispiel-Szenarien

| Szenario | Konfiguration |
| --- | --- |
| **Alles Self-Hosted** | Alle Rollen → `ollama` mit verschiedenen Endpoints (z.B. GPU-Server für Kartograph, CPU-Server für Worker) |
| **Cloud-Mix** | Kartograph=Gemini, Stratege=Claude, Worker=Ollama lokal |
| **Einfach-Modus** | Keine `ai_provider_configs`-Einträge → Fallback auf globalen `app_settings.ai_provider` (wie bisheriges Design) |
| **Schrittweise Migration** | Erst Worker automatisieren (niedrigstes Risiko), dann schrittweise andere Rollen hinzufügen |
| **Worker-Endpoint-Pool** | Worker → `ollama` mit `endpoints` JSONB-Array (3 GPU-Server), `pool_strategy: 'weighted'` — Conductor verteilt Tasks per Round-Robin/Weight auf die Endpoints; ideal für parallele Subtask-Bearbeitung |

### Worker-Endpoint-Pool (optional)

Statt eines einzelnen `endpoint` kann eine Agent-Rolle (typischerweise Worker) ein **Array von Endpoints** konfigurieren. Der Conductor verteilt Dispatches über den Pool:

```text
┌─────────────┬───────────┬──────────┬──────────────────────────────────────────────┬───────────────┐
│ agent_role   │ provider  │ model    │ endpoints                                    │ pool_strategy │
├─────────────┼───────────┼──────────┼──────────────────────────────────────────────┼───────────────┤
│ worker       │ ollama    │ llama3.3 │ [{gpu1:11434, w:1}, {gpu2:11434, w:1},       │ round_robin   │
│              │           │          │  {gpu3:11434, w:2}]                          │               │
└─────────────┴───────────┴──────────┴──────────────────────────────────────────────┴───────────────┘
```

**Pool-Strategien:**

| Strategie | Verhalten |
| --- | --- |
| `round_robin` | Zyklisch über alle healthy Endpoints (Default) |
| `weighted` | Höheres `weight` = mehr Dispatches (z.B. stärkere GPU → weight 2) |
| `least_busy` | Endpoint mit wenigsten aktiven `conductor_dispatches` (status=dispatched) |

**Subtask-Parallelisierung:** Wenn der Architekt einen Task in Subtasks zerlegt hat (`parent_task_id` gesetzt), kann der Conductor mehrere Subtasks **gleichzeitig** an verschiedene Pool-Endpoints dispatchen — begrenzt durch `HIVEMIND_CONDUCTOR_PARALLEL`. Nach Abschluss aller Subtasks erzeugt der Conductor automatisch einen Merge-Prompt (`prompt_type: 'merge_subtasks'`) für den Parent-Task.

**Wann sinnvoll:** Mehrere Consumer-GPUs (RTX 3060/4060) mit Ollama, Tasks die der Architekt gut in unabhängige Subtasks zerlegt hat (z.B. Endpoint A + Endpoint B + Tests). Nicht sinnvoll für stark abhängige Subtasks oder Cloud-Provider (die haben eigenes Load-Balancing).

### Token-Count-Kalibrierung per Provider

Jeder Provider hat leicht unterschiedliche Tokenizer. Die Kalibrierung wird per Provider gesteuert:

```text
HIVEMIND_TOKEN_COUNT_CALIBRATION = {"anthropic": 1.05, "openai": 1.0, "google": 1.1, "ollama": 1.0}
```

Der Bibliothekar multipliziert den gezählten Token-Count mit dem Kalibrierungsfaktor des jeweiligen Providers bevor er das Budget prüft.

> → Datenmodell: [data-model.md — ai_provider_configs](../architecture/data-model.md)
> → UI: [Settings → Tab KI](../ui/views.md)
> → Phase-8-Deliverables: [phase-8.md](../phases/phase-8.md)

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
