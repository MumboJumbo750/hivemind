# Dokumentations-Review: Gaps, Inkonsistenzen & Bottlenecks

← [Index](../masterplan.md)

**Review-Scope:** Alle 37+ Dokumentationsdateien, Seed-Dateien, Phase-Docs, Architektur-Docs, Feature-Docs, UI-Docs, Agent-Docs.

**Bewertungsskala:**
- 🔴 **KRITISCH** — Inkonsistenzen die bei Implementierung zu Bugs oder Blockern führen
- 🟡 **MITTEL** — Fehlende Definitionen die Interpretationsspielraum lassen
- 🟢 **NIEDRIG** — Verbesserungsmöglichkeiten, kosmetische Lücken

---

## 1. Dateninkonsistenzen zwischen Dokumenten

### 🔴 1.1 EXP-Werte: `gamification.md` vs. `phase-5.md`

Die kanonische EXP-Tabelle in [gamification.md](./features/gamification.md) und die Phase-1-Gamification-Spezifikation in [phase-1.md](./phases/phase-1.md#gamification-spezifikation) definieren:

| Event | gamification.md / phase-1.md |
|---|---|
| Task done (approve_review) | +50 |
| Clean Run Bonus | +20 |
| Skill merge | +30 |
| Wiki-Artikel erstellt | +15 |
| Decision Record erstellt | +10 |

[phase-5.md](./phases/phase-5.md) (Zeile 57 — Gamification-Aktivierung) gibt **komplett andere Werte** an:

| Event | phase-5.md |
|---|---|
| approve_review | +100 |
| First-Try-Bonus | +50 |
| merge_skill | +75 |
| create_wiki_article | +50 |
| merge_guard | +50 |
| create_decision_record | +25 |

**Auswirkung:** Implementierer weiß nicht welche Werte gelten. Das Level-System (max 30.000 EXP) ist auf die niedrigeren Werte kalibriert — mit den Phase-5-Werten wäre Level 10 deutlich schneller erreichbar.

**Empfehlung:** Phase-5-Werte auf die kanonische Tabelle in `gamification.md` / `phase-1.md` angleichen und einen expliziten Verweis `→ Kanonische Werte: gamification.md` in Phase 5 setzen.

---

### 🔴 1.2 pgvector-Index-Typ: `memory-ledger.md` (IVFFlat) vs. `data-model.md` (HNSW)

[memory-ledger.md](./features/memory-ledger.md) (Zeile 526-527) definiert im lokalen Schema-Snippet:

```sql
CREATE INDEX idx_memory_entries_embedding ON memory_entries USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_memory_summaries_embedding ON memory_summaries USING ivfflat (embedding vector_cosine_ops);
```

[data-model.md](./architecture/data-model.md) (kanonisches Schema) verwendet durchgehend **HNSW** und begründet die Entscheidung explizit (Zeile 1163-1164):
> Bessere Query-Performance als IVFFlat bei < 1M Vektoren; kein Rebuild nach Inserts nötig.

**Auswirkung:** IVFFlat erfordert regelmäßiges `REINDEX` nach Inserts (Memory Entries sind append-only → häufige Inserts). HNSW ist hier klar besser geeignet.

**Empfehlung:** IVFFlat-Referenz in `memory-ledger.md` auf HNSW korrigieren.

---

### 🟡 1.3 `save_memory` in Phase 1 — aber kein MCP-Server

Drei Dokumente referenzieren `save_memory` als verfügbar ab Phase 1:
- [phase-1.md](./phases/phase-1.md) (Zeile 115)
- [data-model.md](./architecture/data-model.md) (Zeile 1064)
- [memory-ledger.md](./features/memory-ledger.md) (Zeile 552)

Der MCP-Server wird jedoch erst in **Phase 3** implementiert. In Phase 1 gibt es kein MCP.

**Auswirkung:** Unklar ob `save_memory` in Phase 1 als REST-Endpoint (ohne MCP-Wrapper) oder überhaupt nicht verfügbar ist.

**Empfehlung:** Klären: Entweder (a) `save_memory` als REST-Endpoint `POST /api/memory/entries` in Phase 1 anbieten (analog zu den Basis-CRUD-Endpoints), oder (b) Verfügbarkeit auf Phase 3 verschieben. Wenn (a): REST-Endpoint in Phase-1-Deliverables explizit aufnehmen.

---

## 2. Fehlende Schema-Definitionen in `data-model.md`

### 🔴 2.1 `notification_preferences` auf `users`-Tabelle fehlt

Das [Profil-View](./ui/views.md) und die [Feature-Matrix](./ui/feature-matrix.md) referenzieren per-User Notification-Präferenzen als JSONB-Feld. Die [Einstellungs-Hierarchie-Tabelle](./ui/views.md) listet `users.notification_preferences (JSONB)` explizit.

`data-model.md` definiert die `users`-Tabelle mit `preferred_theme`, `preferred_tone`, `avatar_url`, `avatar_frame`, `bio`, `display_name` — aber **kein** `notification_preferences`-Feld.

**Empfehlung:** `notification_preferences JSONB DEFAULT '{}'::jsonb` zur `users`-Tabelle hinzufügen.

---

### 🟡 2.2 `notification_mode` in `app_settings` fehlt

[phase-2.md](./phases/phase-2.md) definiert einen kritischen Cutover-Mechanismus:
> Das Frontend erkennt den Wechsel über `GET /api/settings → { ..., "notification_mode": "client" | "backend" }`.

`data-model.md` listet `notification_mode` **nicht** in der kanonischen `app_settings`-Schlüssel-Tabelle.

**Empfehlung:** `notification_mode` (TEXT, Default: `'client'`, valide: `client|backend`) in die `app_settings`-Schlüssel-Tabelle aufnehmen.

---

### 🟡 2.3 `pgvector_routing_threshold` in `app_settings` fehlt

[phase-7.md](./phases/phase-7.md) referenziert `app_settings.pgvector_routing_threshold` (Default: 0.85) mit Laufzeit-Änderung via `PATCH /api/settings/pgvector_routing_threshold`.

Nicht in `data-model.md` Schlüssel-Tabelle.

**Empfehlung:** Zur kanonischen Schlüssel-Tabelle hinzufügen.

---

### 🟡 2.4 `prompt_history` Retention-Policy nicht in kanonischer Cron-Liste

[phase-3.md](./phases/phase-3.md) definiert:
- Max 500 Einträge pro Task (FIFO)
- Retention-Cron: Einträge älter als `HIVEMIND_PROMPT_HISTORY_RETENTION_DAYS` (Default: 180) werden gelöscht

Weder `data-model.md` noch die Observability-Docs erwähnen diesen Cron-Job in der Cron-Übersicht.

**Empfehlung:** Zur Cron-Referenz hinzufügen (läuft täglich mit Audit-Retention-Job).

---

## 3. Phase-Alignment-Gaps

### 🔴 3.1 Phase F Notifications erfordern Phase 6

[phase-f.md](./phases/phase-f.md) listet 6 Federation-Notification-Types als Deliverables:
`task_delegated`, `peer_task_done`, `peer_online`, `peer_offline`, `federated_skill`, `discovery_session`

Der Notification-Service (der in die `notifications`-Tabelle schreibt) wird erst in **Phase 6** implementiert. Wenn Phase F wie empfohlen nach Phase 2 eingeschoben wird (vor Phase 3), existiert kein Notification-Backend.

**Auswirkung:** Die Phase-F-Notifications können nicht wie definiert funktionieren. Phase 2 nutzt client-calculated Notifications — aber die Federation-Event-Types sind dort nicht berücksichtigt.

**Empfehlung:** Entweder:
- (a) Federation-Notification-Types in den client-calculated Modus aufnehmen (SSE-Events aus Federation-State-Changes ableiten), oder
- (b) explizit dokumentieren, dass Federation-Notifications erst ab Phase 6 funktionieren und Phase F entsprechend annotieren

---

### 🟡 3.2 `hivemind/create_epic` — welche Phase?

[mcp-toolset.md](./architecture/mcp-toolset.md) (Zeile 151) definiert das Tool `hivemind/create_epic`. Es wird in den Admin-Writes referenziert. Aber **keine Phase-Datei listet es als Deliverable**:

- Phase 2 hat REST-CRUD für Epics, aber kein MCP-Tool
- Phase 3 implementiert MCP Read-Tools, keine Write-Tools
- Phase 4 implementiert Planer-Writes — `propose_epic`, `decompose_epic`, aber nicht `create_epic`
- Phase 5 erwähnt es nicht

**Auswirkung:** Unklar wann `create_epic` als MCP-Tool implementiert wird. Das REST-Endpoint `POST /api/epics` existiert vermutlich ab Phase 2, aber der MCP-Wrapper hat keinen Phasen-Zuordnung.

**Empfehlung:** `hivemind/create_epic` explizit Phase 4 oder Phase 2 zuordnen. Da es ein Admin-Write ist, empfiehlt sich Phase 4 (zusammen mit den anderen Planer-Writes).

---

### 🟡 3.3 `discard_dead_letter` MCP-Tool — welche Phase?

[mcp-toolset.md](./architecture/mcp-toolset.md) definiert `hivemind/discard_dead_letter`, aber keine Phase-Datei listet es als Deliverable. `requeue_dead_letter` ist Phase 7 zugeordnet.

**Empfehlung:** `discard_dead_letter` als Phase-7-Deliverable `hivemind/discard_dead_letter` neben `requeue_dead_letter` aufnehmen.

---

### 🟡 3.4 DB-Trigger für `epic_key` / `task_key` Immutability — nicht in Phase-1-Deliverables

`data-model.md` spezifiziert Immutability-Trigger für `epic_key` und `task_key` (automatisch generierte Keys dürfen nicht geändert werden). Phase 1 erstellt alle Tabellen, erwähnt aber die Trigger-Erstellung nicht in den Deliverables.

**Empfehlung:** In Phase-1a-Deliverables ergänzen: "DB-Trigger für `epic_key` und `task_key` Immutability gemäß data-model.md".

---

### 🟡 3.5 `idempotency_keys` Cleanup-Cron fehlt

`data-model.md` definiert `idempotency_keys` mit 24h TTL. Kein Phase-Doc und kein Cron-Job-Katalog erwähnt den Cleanup.

**Empfehlung:** Cron-Job in Phase 2 (wo Idempotenz als Deliverable steht) ergänzen: täglicher Cleanup von `idempotency_keys` älter als 24h.

---

## 4. Fehlende Definitionen / Unterspezifizierte Bereiche

### 🔴 4.1 `reviewer` Actor-Rolle fehlt in `rbac.md`

[rbac.md](./architecture/rbac.md) definiert 4 Actor-Rollen: `developer`, `admin`, `service`, `kartograph`.

`data-model.md` (Zeile 225, 281) und Phase 8 führen `reviewer` als 5. Rolle ein. `rbac.md` erwähnt die Rolle nicht — weder als geplante noch als Phase-8-Erweiterung.

**Auswirkung:** Die Berechtigungsmatrix in `rbac.md` ist unvollständig für Phase 8.

**Empfehlung:** In `rbac.md` einen Abschnitt "Phase-8-Erweiterung: reviewer-Rolle" mit Berechtigungsmatrix-Zeile ergänzen. Der Reviewer darf nur `submit_review_recommendation` — alle anderen Writes sind verboten.

---

### 🟡 4.2 Keine Env-Variable-Gesamtreferenz

Env-Variablen sind über >15 Dokumentdateien verstreut:
- `observability.md`: `HIVEMIND_LOG_*`, `HIVEMIND_METRICS_*`, `HIVEMIND_OTEL_*`
- `phase-f.md`: `HIVEMIND_FEDERATION_*`, `HIVEMIND_HIVE_STATION_*`
- `phase-3.md`: `HIVEMIND_EMBEDDING_*`
- `phase-6.md`: `HIVEMIND_SLA_CRON_INTERVAL`, `NOTIFICATION_RETENTION_DAYS`
- `phase-8.md`: `HIVEMIND_CONDUCTOR_*`, `HIVEMIND_AI_*`, `HIVEMIND_KEY_PASSPHRASE`
- `gamification.md`: `HIVEMIND_EXP_*`
- `federation.md`: `HIVEMIND_FEDERATION_PING_INTERVAL`, `HIVEMIND_FEDERATION_OFFLINE_THRESHOLD`
- etc.

Es gibt **keine konsolidierte Env-Var-Referenz**.

**Auswirkung:** Bei Deployment-Konfiguration fehlt ein single source of truth. Doppelte/inkonsistente Defaults sind wahrscheinlich.

**Empfehlung:** Ein neues Dokument `docs/architecture/env-reference.md` mit allen Env-Variablen, Defaults, und Quellverweis erstellen. Alternativ: `observability.md` Konfigurationstabelle als Basis erweitern.

---

### 🟡 4.3 SSE Stream-Token Lifetime unspezifiziert

[rest-api.md](./architecture/rest-api.md) definiert den Stream-Token-Handshake (`POST /api/auth/stream-token`), aber spezifiziert nicht:
- Token-Lebensdauer (wie lange ist der Stream-Token gültig?)
- Verhalten bei Token-Ablauf während aktivem SSE-Stream
- Max. parallele Streams pro User

**Empfehlung:** Stream-Token-Lifetime (z.B. 24h oder session-gebunden) und Max-Connections-pro-User definieren.

---

### 🟡 4.4 Multi-Projekt Kontextwechsel UI-Verhalten unklar

`architecture/overview.md` beschreibt Multi-Projekt-Support mit Project-Switcher. Aber:
- Was passiert mit dem aktiven Prompt in der Prompt Station beim Projekt-Wechsel?
- Wird die Queue pro Projekt getrennt?
- Wird der Memory-Ledger-Scope automatisch gewechselt?

**Empfehlung:** In `ui/concept.md` oder `ui/views.md` einen Abschnitt "Projekt-Wechsel-Verhalten" mit explizitem Verhalten pro View ergänzen.

---

### 🟡 4.5 Token-Budget vs. Provider Context Window — keine Validierung

[phases/overview.md](./phases/overview.md) definiert die Token-Budget-Präzedenz:
1. `context_boundaries.max_token_budget` (Task-spezifisch)
2. `HIVEMIND_TOKEN_BUDGET_PROVIDER_OVERRIDE` (per Provider)
3. `app_settings.token_budget_default` (8000)

Aber: Wenn ein Provider (z.B. Ollama mit einem 4k-Modell) ein kleineres Context Window hat als das konfigurierte Budget, gibt es keine Validierung. Das Prompt-Assembly würde einen zu großen Prompt generieren.

**Empfehlung:** In Phase 8 (Provider-Integration) eine Validierung einbauen: `effective_budget = min(configured_budget, provider_context_window)`. Provider-Limits als optionales Feld in `ai_provider_configs` aufnehmen.

---

### 🟢 4.6 `token_count_minified` in `prompt_history` — undokumentiert

`data-model.md` definiert `token_count_minified` auf `prompt_history`, aber kein Dokument erklärt was "minified" bedeutet oder wann/wie es berechnet wird.

**Empfehlung:** Kurze Definition in `data-model.md` inline ergänzen (z.B. "Token-Count nach Whitespace-Reduktion und Comment-Stripping").

---

### 🟢 4.7 `skill_versions.token_count` — Initial-Berechnung unklar

Token-Counts werden laut Spec "beim Merge/Version-Update einmalig berechnet". Aber bei `propose_skill` (Draft → pending_merge) wird kein Token-Count berechnet. Das bedeutet: während der Review-Phase im Triage-System ist kein Token-Count sichtbar.

**Empfehlung:** Token-Count bei `submit_skill_proposal` berechnen (sichtbar für Admin-Review).

---

## 5. Architektur-Bottlenecks & Risiken

### 🟡 5.1 Single Ollama Instance als Bottleneck für Phase 8

Phase 3 acknowledged das Limit eines einzelnen Ollama-Containers. In Phase 8 gibt es Worker-Endpoint-Pools für AI-Provider, aber **nicht für Embedding-Berechnung**. Der Embedding-Service nutzt weiterhin eine einzelne Ollama-Instanz.

Bei autonomem Betrieb (Phase 8) mit parallelen Conductor-Dispatches werden gleichzeitig:
- Worker-Prompts an AI-Provider geschickt → verschiedene Endpoints (skaliert)
- Embedding-Berechnung für neue Skills/Wiki → eine Ollama-Instanz (Flaschenhals)

**Empfehlung:** Embedding-Pool-Support analog zu `ai_provider_configs.endpoints` evaluieren, oder OpenAI-Embeddings als Fallback bei Ollama-Auslastung priorisieren.

---

### 🟡 5.2 Synchrone Gamification Post-Commit-Hooks

Phase 1 Gamification-Spec definiert EXP/Badge/Level-Checks als **synchrone** Post-Commit-Hooks:

```python
async def on_task_done(task, actor_id):
    await add_exp(...)
    await check_badges(...)
    await check_level_up(...)
```

Bei vielen Badges und komplexen Bedingungen (z.B. `iron_will` erfordert vorherige `escalated`-Phase + `qa_failed_count >= 3`) könnten diese Checks die Response-Latenz der Write-Endpoints erhöhen.

**Empfehlung:** Gamification-Checks als async Background-Task (nach Response) ausführen. EXP-Addition kann synchron bleiben (schnell), aber Badge-Checks und Level-Up-Prüfung async. SSE `level_up`/`badge_awarded` Events werden dann mit leichter Verzögerung ausgeliefert.

---

### 🟡 5.3 Phase 5 — Größte Phase ohne formalen Split

Phase 5 listet als Deliverables:
- Worker-Write-Tools (6 Tools)
- Gaertner-Write-Tools (5 Tools)
- Kartograph-Write-Tools (7 Tools)
- Review-Write-Tools (2 Tools)
- Admin-Write-Tools (12+ Tools)
- Wiki View (Frontend)
- Nexus Grid 2D (Frontend)
- Gamification-Aktivierung (Backend + Frontend)

Das Dokument schlägt 5a/5b Split vor, aber **nur als Empfehlung** — kein formaler Split mit eigenen Acceptance Criteria pro Sub-Phase.

**Empfehlung:** 5a/5b Split formalisieren mit separaten Acceptance Criteria wie bei Phase 1a/1b. Die bestehende Tabelle ist ein guter Startpunkt.

---

### 🟢 5.4 SSE Connection Limits unspezifiziert

Für Team-Modus mit vielen gleichzeitigen Usern könnte die SSE-Connection-Zahl zum Problem werden (jeder User hält mindestens 2-3 SSE-Connections offen). Kein Limit definiert.

**Empfehlung:** Max-SSE-Connections als Env-Var (z.B. `HIVEMIND_SSE_MAX_CONNECTIONS`, Default: 100) und Verhalten bei Überschreitung (älteste Connection schließen) definieren.

---

### 🟢 5.5 Database Connection Pool Konfiguration fehlt

asyncpg + SQLAlchemy 2 erfordert Pool-Konfiguration. Keine Env-Var oder Dokumentation für:
- `pool_size`
- `max_overflow`
- `pool_timeout`
- `pool_recycle`

**Empfehlung:** Standard-Werte in `architecture/overview.md` oder `.env.example` dokumentieren.

---

## 6. Edge Cases & Loopholes

### 🟡 6.1 Phase 5: `blocked` Tasks ohne Auflösung

Phase 5 implementiert `create_decision_request` (Task → blocked), aber `resolve_decision_request` kommt erst in Phase 6. Der Workaround ist Admin-Direkt-Intervention via `PATCH /api/tasks/:task_key/state`.

**Problem:** Dieser Workaround:
- Umgeht die Decision-Request-Auflösungs-Logik (kein `decision_records`-Eintrag)
- Setzt den Task auf `in_progress` ohne den Decision Request aufzulösen (Request bleibt `open` in DB)
- Kein Audit-Trail für die Entscheidung

**Empfehlung:** In Phase 5 einen minimalen `resolve_decision_request` implementieren (Admin-only, ohne SLA-Chain). Oder: Decision-Request-Erstellung auf Phase 6 verschieben (Worker meldet Blocker dann nur als Kommentar).

---

### 🟡 6.2 `qa_failed → escalated` Transition-Semantik inkonsistent

[phase-1.md](./phases/phase-1.md) State Machine Code zeigt:
```python
"qa_failed": ["in_progress", "escalated"]
```

Dies suggeriert `escalated` als direkten erlaubten Übergang. Aber der gleiche Abschnitt und `state-machine.md` beschreiben es als **System-Intercept**: Der Worker versucht `qa_failed → in_progress`, und das System fängt ab → setzt stattdessen `escalated`.

**Auswirkung:** In der `ALLOWED_TRANSITIONS`-Map ist `escalated` als expliziter Übergang gelistet — ein Entwickler könnte annehmen, dass ein User direkt `qa_failed → escalated` aufrufen darf.

**Empfehlung:** Entweder:
- (a) `escalated` aus `ALLOWED_TRANSITIONS["qa_failed"]` entfernen und als reinen System-Intercept dokumentieren, oder
- (b) In der Map belassen aber mit Kommentar `# SYSTEM ONLY — nicht direkt aufrufbar` und im Endpoint validieren

---

### 🟡 6.3 `epic_id` Parameter-Naming in MCP-Tools — Key vs. UUID

MCP-Tools verwenden `epic_id` als Parameter-Name, übergeben aber teils **Keys** (Strings wie `"EPIC-12"`):
- `hivemind/assign_bug { "bug_id": "uuid", "epic_id": "EPIC-12" }` — Key
- `hivemind/create_epic_doc { "epic_id": "EPIC-12", ... }` — Key
- `hivemind/propose_epic { "project_id": "uuid", ... }` — UUID

Die DB-Spalte `epic_id` ist UUID. Der MCP-Layer muss Keys zu UUIDs auflösen.

**Auswirkung:** Inkonsistente API-Konvention. Entwickler müssen raten ob `epic_id` einen Key oder eine UUID erwartet.

**Empfehlung:** Konvention klären in `mcp-toolset.md`: "Alle `*_id`-Parameter akzeptieren sowohl UUID als auch Key (EPIC-12, TASK-88). Backend resolvet automatisch." Oder: umbenennen zu `epic_key` bei Key-Parametern.

---

### 🟢 6.4 Wiki-Kategorien-Management nicht spezifiziert

`data-model.md` definiert `wiki_categories` mit hierarchischem `parent_id`. Aber kein Dokument spezifiziert:
- Wie Kategorien erstellt/verschoben werden
- Ob ein MCP-Tool dafür existiert
- Wer Kategorien verwalten darf (RBAC)
- Max-Tiefe der Hierarchie

**Empfehlung:** Kategorie-CRUD in Phase 5 Wiki-Deliverables ergänzen (Admin-only, max 3 Ebenen).

---

### 🟢 6.5 Avatar-Upload: `HIVEMIND_UPLOAD_DIR` nicht in Env-Referenz

Das Profil-System referenziert `HIVEMIND_UPLOAD_DIR/avatars/<uuid>.webp`, aber die Variable fehlt in allen Env-Var-Listen und Docker Compose Konfigurationen.

**Empfehlung:** `HIVEMIND_UPLOAD_DIR` (Default: `/app/uploads`) zur Docker Compose Volume-Config und Env-Referenz hinzufügen.

---

## 7. Positiv-Befunde (keine Maßnahme nötig)

Folgende Bereiche sind exzellent spezifiziert und konsistent:

- **State Machine:** Task + Epic State-Transitions sind zwischen `state-machine.md`, Phase-1 Code und MCP-Toolset konsistent. Eskalations-Pfade sind klar.
- **Federation-Protokoll:** Ed25519-Signatur, Key-Rotation mit Grace-Period, 3 Topologien, Offline-Verhalten — sehr durchdacht.
- **Data Model:** Mit 1300+ Zeilen extrem detailliert. Indexes, Constraints, JSONB-Schemas alle definiert.
- **Guard-System:** Scope-Hierarchie (global → project → skill → task), Lifecycle, Phase-Timeline — vollständig.
- **Autonomy Loop:** Conductor + Reviewer + Governance-Levels bilden ein schlüssiges System. "Review-Gate never removed" als Invariante durchgängig respektiert.
- **UI Component Architecture:** 4 Schichten (Design → UI Primitives → Domain → Views) mit Reuse-Matrix — vorbildlich.
- **Progressive Disclosure:** Konsistent durch alle Phasen. Kein Feature wird aktiviert das eine spätere Phase voraussetzt.
- **Seed Strategy:** Selbst-Bootstrapping als Dogfooding — elegant und vollständig spezifiziert.

---

## Zusammenfassung

| Schwere | Anzahl | Kategorien |
|---|---|---|
| 🔴 Kritisch | 5 | EXP-Werte Widerspruch, Index-Typ Inkonsistenz, save_memory Phase-Mismatch, Phase-F Notifications ohne Backend, notification_preferences fehlt |
| 🟡 Mittel | 16 | Fehlende app_settings-Keys, Phase-Zuordnungslücken, RBAC-Erweiterung, Env-Referenz, Edge Cases |
| 🟢 Niedrig | 6 | Kosmetische Definitionen, Pool-Config, Upload-Dir, Kategorien-CRUD |
| ✅ Positiv | 8 | State Machine, Federation, Data Model, Guards, Autonomy Loop, UI Architecture, Progressive Disclosure, Seed Strategy |

**Empfohlene Prioritätsreihenfolge für Fixes:**
1. EXP-Werte in `phase-5.md` korrigieren (1.1) — 5 Min
2. IVFFlat → HNSW in `memory-ledger.md` (1.2) — 2 Min
3. `notification_preferences` zu `data-model.md` users-Tabelle (2.1) — 5 Min
4. `notification_mode` und `pgvector_routing_threshold` zu `app_settings` (2.2, 2.3) — 5 Min
5. Phase-F Notification-Strategie klären (3.1) — 15 Min
6. `reviewer`-Rolle in `rbac.md` aufnehmen (4.1) — 10 Min
7. Env-Variable-Gesamtreferenz erstellen (4.2) — 30 Min
