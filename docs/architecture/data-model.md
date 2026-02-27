# Datenmodell

← [Index](../../masterplan.md)

Alle Tabellen werden in Phase 1 erstellt (auch wenn viele Spalten erst später befüllt werden). Keine späteren Migrations-Überraschungen.

> **Design-Entscheidung — Vollständiges Schema ab Phase 1:**
> Bewusst gewählt statt inkrementellem Schema-Aufbau. Vorteile: (1) Keine Breaking Migrations zwischen Phasen — Alembic läuft von Anfang an im Auto-Generate-Modus und produziert nur additive `ALTER TABLE`-Statements für spätere Feinjustierungen, (2) Federation-Felder (`origin_node_id`, `federation_scope`, `assigned_node_id`) sind ab Tag 1 Teil der FK-Kette und müssen nicht nachträglich in bestehende Tabellen injiziert werden, (3) Jede Phase kann sofort ihre Features implementieren ohne auf Schema-Erweiterungen warten zu müssen.
> **Alternativen erwogen:** *Inkrementelles Schema* (nur Tabellen der aktuellen Phase anlegen, Rest per Migration in späteren Phasen) — verworfen weil Federation-FKs dann nachträgliche NOT-NULL-Migrations auf Tabellen mit Bestandsdaten erfordern. *Schema-per-Phase-Feature-Flags* (Tabellen existieren, aber Spalten werden per Feature-Flag ignoriert) — unnötige Komplexität, da NULL-Spalten in PostgreSQL keinen Storage-Overhead verursachen.

---

## Tabellen-Übersicht

```text
-- Federation (zuerst — keine Dependencies außer sich selbst)
nodes
node_identity

-- Core
users
app_settings               → users
level_thresholds
badge_definitions
projects
project_members            → users, projects
user_achievements          → users, badge_definitions
epics                      → projects, users, nodes (origin_node_id)
tasks                      → epics, users, nodes (assigned_node_id), (self-ref für Subtasks)
skills                     → projects, users, nodes (origin_node_id)
skill_versions             → skills, users
skill_parents              → skills (child → parent, Composition)
skill_change_proposals     → skills, users             (nach skills — FK auf skills.id)
guard_change_proposals     → guards, users             (nach task_guards — FK auf guards.id)
docs                       → epics, users
context_boundaries         → tasks, users
wiki_categories            (self-ref für parent_id)
wiki_articles              → wiki_categories, users, nodes (origin_node_id)
wiki_versions              → wiki_articles, users
code_nodes                 → projects, users
code_edges                 → projects, code_nodes
node_bug_reports           → code_nodes
epic_node_links            → epics, code_nodes
task_node_links            → tasks, code_nodes
mcp_invocations            → users
idempotency_keys           → users
prompt_history             → projects, epics, tasks, users
sync_outbox                (target_node_id → nodes optional)
sync_dead_letter           → sync_outbox, users
decision_requests          → tasks, epics, users
decision_records           → epics, decision_requests, users
epic_restructure_proposals → epics, users
epic_proposals              → projects, users (Stratege)
guards                     → projects, skills, users
task_guards                → tasks, guards, users
review_recommendations     → tasks, users
conductor_dispatches       (standalone, Audit-Trail)
notifications              → users
```

> `task_skill_pins` existiert **nicht** als eigene Tabelle. Skills werden via `tasks.pinned_skills JSONB` versioniert gepinnt (siehe JSONB-Schemas unten).

---

## Schema

```sql
-- gen_random_uuid() ist in PostgreSQL 13+ built-in — keine Extension nötig
-- Nur pgvector wird als Extension benötigt
CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────
-- FEDERATION: Nodes & Identität
-- ─────────────────────────────────────────────

-- Alle bekannten Peer-Nodes (auch der eigene Node kann hier stehen)
CREATE TABLE nodes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  node_name   TEXT NOT NULL,        -- "alex-hivemind", "ben-hivemind"
  node_url    TEXT NOT NULL UNIQUE,  -- "http://192.168.1.10:8000" — eindeutig pro Node
  public_key  TEXT UNIQUE,           -- Ed25519 Public Key (PEM) — NULL bis Key-Exchange; eindeutig wenn gesetzt
  status      TEXT NOT NULL DEFAULT 'active', -- active|inactive|blocked|removed
  -- active:   Peer ist verbunden und funktional
  -- inactive: Peer ist nicht erreichbar (automatisch via Heartbeat)
  -- blocked:  Admin hat Peer blockiert (reversibel, kein Sync)
  -- removed:  Admin hat Peer endgültig entfernt (irreversibel, Audit-Trail bleibt)
  last_seen   TIMESTAMPTZ,          -- letzter erfolgreicher /federation/ping
  deleted_at  TIMESTAMPTZ,          -- Soft-Delete: gesetzt bei Entfernung, Peer bleibt für Audit sichtbar
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Identität dieser Node (genau 1 Zeile)
-- Wird beim ersten Start auto-generiert wenn noch nicht vorhanden
-- Single-Row-Enforcement: node_id referenziert die eigene Zeile in nodes + singleton_guard erzwingt max. 1 Zeile
CREATE TABLE node_identity (
  node_id        UUID PRIMARY KEY REFERENCES nodes(id),  -- FK auf eigenen Eintrag in nodes
  singleton_guard BOOLEAN NOT NULL DEFAULT true UNIQUE CHECK (singleton_guard = true),
  -- singleton_guard: UNIQUE + CHECK(true) garantiert exakt 0 oder 1 Zeile
  node_name   TEXT NOT NULL,
  private_key TEXT NOT NULL,  -- Ed25519 Private Key (PEM, at-rest verschlüsselt via HIVEMIND_KEY_PASSPHRASE)
  public_key  TEXT NOT NULL,  -- Ed25519 Public Key (PEM)
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- CORE: Users & Projects
-- ─────────────────────────────────────────────

CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username      TEXT NOT NULL UNIQUE,
  email         TEXT UNIQUE,
  password_hash TEXT,           -- argon2; NULL für service-Accounts (API-Key-Auth) und Solo-Modus ohne Login
  api_key_hash  TEXT UNIQUE,    -- SHA-256 Hash des API-Keys; nur für role='service'; NULL für alle anderen
  role          TEXT NOT NULL DEFAULT 'developer', -- developer|admin|service|kartograph
  exp_points    INT NOT NULL DEFAULT 0,            -- Gamification Progression
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- SYSTEM-KONFIGURATION (nach users — FK auf users.id)
-- ─────────────────────────────────────────────

CREATE TABLE app_settings (
  key        TEXT PRIMARY KEY,   -- z.B. "hivemind_mode", "routing_threshold"
  value      TEXT NOT NULL,
  version    INT NOT NULL DEFAULT 0,
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Bootstrap-Eintrag (wird in Phase 1-Migration gesetzt):
-- INSERT INTO app_settings (key, value) VALUES ('hivemind_mode', 'solo');

-- Kanonische Key-Liste (alle erwarteten Keys mit Typ und Default):
-- | Key                                  | Typ     | Default          | Phase | Beschreibung                                      |
-- |--------------------------------------|---------|------------------|-------|---------------------------------------------------|
-- | hivemind_mode                        | TEXT    | 'solo'           | 1     | solo|team — Laufzeit-Switch via Settings           |
-- | current_phase                        | INT     | 1                | 1     | Aktive Phase (1-8); steuert Feature-Gates          |
-- | federation_enabled                   | BOOLEAN | false            | F     | Federation aktiviert (überschreibt Env-Var nach Bootstrap) |
-- | federation_topology                  | TEXT    | 'direct_mesh'    | F     | direct_mesh|hub_assisted|hub_relay                 |
-- | token_budget_default                 | INT     | 8000             | 3     | Default Token-Budget für Prompt-Assembly            |
-- | routing_threshold                    | FLOAT   | 0.5              | 7     | pgvector Similarity-Schwelle für Auto-Routing       |
-- | sla_cron_interval_minutes            | INT     | 60               | 6     | SLA-Check-Intervall in Minuten                      |
-- | audit_retention_payload_days         | INT     | 90               | 2     | Tage bis Audit Payload gelöscht wird                |
-- | audit_retention_summary_days         | INT     | 365              | 2     | Tage bis Audit Summary gelöscht wird                |
-- | notification_retention_days          | INT     | 90               | 2     | Tage bis Notifications gelöscht werden              |
-- | embedding_provider                   | TEXT    | 'ollama'         | 3     | ollama|openai — Embedding-Provider                  |
-- | embedding_model                      | TEXT    | 'nomic-embed-text'| 3    | Modell-Name beim Provider                           |
-- | ai_provider                          | TEXT    | NULL             | 8     | anthropic|openai|google|ollama — Global-Default AI-Provider für Auto-Modus (Fallback wenn kein ai_provider_configs-Eintrag) |
-- | ai_rpm_limit                         | INT     | 10               | 8     | Max Requests/Minute an AI-Provider (Global-Default)  |
-- | cross_project_alerts                 | BOOLEAN | true             | 2     | SLA/Eskalationen projektübergreifend anzeigen       |
-- | guard_execution_allowlist            | TEXT[]  | siehe guards.md  | 8     | Erlaubte Guard-Commands für Auto-Execution          |
-- | guard_timeout_seconds                | INT     | 120              | 8     | Timeout für Guard-Auto-Execution                    |
-- | backup_cron                          | TEXT    | '0 2 * * *'      | 1     | Cron-Expression für Backup                          |
-- | backup_retention_daily               | INT     | 7                | 1     | Anzahl täglicher Backups                            |
-- | backup_retention_weekly              | INT     | 4                | 1     | Anzahl wöchentlicher Backups                        |
-- | backup_admin_id                      | UUID    | NULL             | 6     | Fallback-Admin bei Inaktivität (> 48h kein Login/Write) |
-- | triage_delegates                     | UUID[]  | '{}'             | 7     | User-IDs mit delegierten Triage-Rechten (neben Admin) |
-- | ai_api_key_encrypted                 | TEXT    | NULL             | 8     | AI-Provider API-Key (AES-256-GCM verschlüsselt) — Global-Fallback, per-Role Keys in ai_provider_configs |
-- | ai_api_key_nonce                     | TEXT    | NULL             | 8     | AES-GCM Nonce für ai_api_key_encrypted              |
-- | memory_token_ratio                   | FLOAT   | 0.3              | 3     | Max. Anteil des Token-Budgets für Memory-Kontext (0.0–1.0) |
-- | governance                             | JSONB   | siehe unten      | 8     | Governance-Levels pro Entscheidungstyp (manual/assisted/auto) |
--
-- governance Default-JSON:
-- {
--   "review":           { "level": "manual", "confidence_threshold": 0.85, "grace_minutes": 15 },
--   "epic_proposal":     { "level": "manual", "confidence_threshold": 0.80, "grace_minutes": 30 },
--   "epic_scoping":      { "level": "manual" },
--   "skill_merge":       { "level": "manual", "confidence_threshold": 0.90, "grace_minutes": 30 },
--   "guard_merge":       { "level": "manual", "confidence_threshold": 0.90, "grace_minutes": 30 },
--   "decision_request":  { "level": "manual" },
--   "escalation":        { "level": "manual" }
-- }
-- → Vollständige Spezifikation: docs/features/autonomy-loop.md#3-governance-levels

-- ─────────────────────────────────────────────
-- AI-PROVIDER: Per-Agent-Role Provider-Routing (Phase 8)
-- ─────────────────────────────────────────────

-- Jede Agent-Rolle kann einen eigenen AI-Provider nutzen.
-- Nicht-konfigurierte Rollen fallen auf app_settings.ai_provider (Global-Default) zurück.
-- Kein Global-Default → BYOAI-Modus (User kopiert Prompt manuell).
-- → Bibliothekar-Integration: docs/agents/bibliothekar.md#agent-provider-routing

CREATE TABLE ai_provider_configs (
  agent_role        TEXT PRIMARY KEY,        -- kartograph|stratege|architekt|worker|gaertner|triage
  provider          TEXT NOT NULL,           -- anthropic|openai|google|ollama|custom
  model             TEXT NOT NULL,           -- z.B. claude-sonnet-4, gpt-4o, gemini-2.5-pro, llama3.3
  endpoint          TEXT,                    -- Custom-Endpoint-URL (Pflicht bei ollama/custom; NULL → Standard-Endpoint)
  api_key_encrypted TEXT,                    -- AES-256-GCM verschlüsselt (selbes System wie app_settings.ai_api_key_encrypted; NULL bei Ollama)
  api_key_nonce     TEXT,                    -- AES-GCM Nonce
  token_budget      INT NOT NULL DEFAULT 8000, -- Token-Budget für diese Rolle (überschreibt app_settings.token_budget_default)
  rpm_limit         INT NOT NULL DEFAULT 10,   -- Max Requests/Minute für diese Rolle
  enabled           BOOLEAN NOT NULL DEFAULT true, -- Deaktiviert → BYOAI-Fallback für diese Rolle
  updated_by        UUID REFERENCES users(id),
  updated_at        TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT valid_agent_role CHECK (agent_role IN ('kartograph', 'stratege', 'architekt', 'worker', 'gaertner', 'triage', 'reviewer')),
  CONSTRAINT valid_provider CHECK (provider IN ('anthropic', 'openai', 'google', 'ollama', 'custom')),
  CONSTRAINT endpoint_required_for_local CHECK (
    (provider NOT IN ('ollama', 'custom')) OR (endpoint IS NOT NULL)
  )
);

-- Beispiel-Konfiguration (Mixed Cloud + Self-Hosted):
-- INSERT INTO ai_provider_configs (agent_role, provider, model, endpoint, token_budget, rpm_limit) VALUES
--   ('kartograph', 'google',    'gemini-2.5-pro',   NULL,                         200000, 5),
--   ('stratege',   'anthropic', 'claude-sonnet-4',   NULL,                         100000, 10),
--   ('architekt',  'openai',    'gpt-4o',            NULL,                         128000, 10),
--   ('worker',     'ollama',    'llama3.3',          'http://gpu-server:11434',    8000,   30),
--   ('gaertner',   'anthropic', 'claude-sonnet-4',   NULL,                         100000, 10),
--   ('triage',     'ollama',    'llama3.3',          'http://gpu-server:11434',    8000,   30);

-- ─────────────────────────────────────────────
-- REVIEW RECOMMENDATIONS: AI-Review-Empfehlungen (Phase 8)
-- ─────────────────────────────────────────────

CREATE TABLE review_recommendations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id         UUID NOT NULL REFERENCES tasks(id),
  recommendation  TEXT NOT NULL,           -- approve|reject|needs_human_review
  confidence      FLOAT NOT NULL,          -- 0.0–1.0
  summary         TEXT NOT NULL,           -- Freitext-Zusammenfassung
  checklist       JSONB NOT NULL DEFAULT '[]',  -- [{ "criterion": "...", "met": true/false }]
  concerns        JSONB NOT NULL DEFAULT '[]',  -- ["Concern 1", "Concern 2"]
  grace_until     TIMESTAMPTZ,             -- NULL bei manual/assisted; Zeitstempel bei auto
  accepted_by     UUID REFERENCES users(id), -- NULL = noch offen; User-ID bei manueller Bestätigung
  accepted_at     TIMESTAMPTZ,
  overridden      BOOLEAN NOT NULL DEFAULT false, -- true wenn Owner überschrieben hat
  created_at      TIMESTAMPTZ DEFAULT now(),
  CONSTRAINT valid_recommendation CHECK (recommendation IN ('approve', 'reject', 'needs_human_review')),
  CONSTRAINT valid_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_review_recommendations_task ON review_recommendations(task_id);
CREATE INDEX idx_review_recommendations_pending ON review_recommendations(grace_until)
  WHERE accepted_by IS NULL AND overridden = false AND grace_until IS NOT NULL;

-- ─────────────────────────────────────────────
-- CONDUCTOR DISPATCHES: Audit-Trail für Agent-Dispatching (Phase 8)
-- ─────────────────────────────────────────────

CREATE TABLE conductor_dispatches (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trigger_event   TEXT NOT NULL,           -- z.B. 'task.state.in_review', 'epic.state.incoming'
  trigger_entity_id UUID,                  -- Task-ID, Epic-ID, Outbox-ID etc.
  agent_role      TEXT NOT NULL,           -- kartograph|stratege|architekt|worker|gaertner|triage|reviewer
  prompt_type     TEXT NOT NULL,           -- Der generierte Prompt-Typ
  provider        TEXT,                    -- Genutzter AI-Provider (NULL bei BYOAI-Fallback)
  status          TEXT NOT NULL DEFAULT 'dispatched', -- dispatched|completed|failed|vetoed
  error_message   TEXT,                    -- Fehlerdetails bei status=failed
  duration_ms     INT,                     -- Laufzeit in Millisekunden (NULL bis completed/failed)
  idempotency_key TEXT NOT NULL UNIQUE,    -- Verhindert doppeltes Dispatching
  created_at      TIMESTAMPTZ DEFAULT now(),
  completed_at    TIMESTAMPTZ,
  CONSTRAINT valid_dispatch_status CHECK (status IN ('dispatched', 'completed', 'failed', 'vetoed'))
);

CREATE INDEX idx_conductor_dispatches_status ON conductor_dispatches(status) WHERE status = 'dispatched';
CREATE INDEX idx_conductor_dispatches_entity ON conductor_dispatches(trigger_entity_id);
CREATE INDEX idx_conductor_dispatches_created ON conductor_dispatches(created_at DESC);

CREATE TABLE projects (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,
  description TEXT,
  created_by  UUID NOT NULL REFERENCES users(id),
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE project_members (
  project_id  UUID NOT NULL REFERENCES projects(id),
  user_id     UUID NOT NULL REFERENCES users(id),
  role        TEXT NOT NULL DEFAULT 'developer', -- developer|admin|service|kartograph
  PRIMARY KEY (project_id, user_id)
);

-- ─────────────────────────────────────────────
-- GAMIFICATION: Levels, Badges, Achievements
-- ─────────────────────────────────────────────

-- Gamification-Skeleton — Schema ab Phase 1; Seeds (level_thresholds, badge_definitions) in Phase-1-Migration;
-- EXP-Vergabe + Achievement-Trigger aktiv ab Phase 2 (erste Writes mit Audit).
-- Phase 1: Tabellen + Bootstrap-Seeds vorhanden, aber kein EXP-Vergabecode aktiv.
-- Phase 2+: approve_review / reject_review / merge_skill etc. vergeben EXP gemäß EXP-Vergabe-Regeln (s.u.).
-- UI-Anzeige (EXP-Bar in Status Bar, Achievement-Badges): ab Phase 2.

-- Level-Schwellen-Konfiguration (Commander Ranks)
-- Wird beim Bootstrap mit Default-Werten gefüllt; Admin kann anpassen.
CREATE TABLE level_thresholds (
  level        INT PRIMARY KEY,            -- 1, 2, 3, ...
  exp_required INT NOT NULL,               -- Kumulative EXP für dieses Level
  rank_name    TEXT NOT NULL,              -- z.B. "Recruit", "Operative", "Commander", "Strategist", "Grandmaster"
  unlocks      TEXT                         -- Kosmetische Freischaltung (z.B. "theme:operator-mono", "avatar:gold-frame")
);
-- Bootstrap-Daten:
-- INSERT INTO level_thresholds VALUES
--   (1,     0, 'Recruit',    NULL),
--   (2,   100, 'Operative',  NULL),
--   (3,   300, 'Specialist', NULL),
--   (4,   600, 'Commander',  NULL),
--   (5,  1000, 'Strategist', 'avatar:silver-frame'),
--   (6,  1500, 'Veteran',    NULL),
--   (7,  2200, 'Elite',      'theme:operator-mono'),
--   (8,  3000, 'Mastermind', 'avatar:gold-frame'),
--   (9,  4000, 'Legend',     NULL),
--   (10, 5000, 'Grandmaster','avatar:holo-frame');

-- EXP-Vergabe-Regeln (kanonisch):
-- | Event                          | EXP  | Bedingung                        |
-- |--------------------------------|------|----------------------------------|
-- | Task → done                    |  50  | Basis                            |
-- | Task → done (HIGH Priority)    | +25  | Bonus                            |
-- | Task → done (Eskalation gelöst)|+100  | resolve_escalation vorher        |
-- | Skill gemergt                  |  30  | merge_skill                      |
-- | Wiki-Artikel erstellt          |  20  | create_wiki_article              |
-- | Decision Request gelöst <24h   |  15  | resolve_decision_request         |
-- | 500 Code-Nodes kartiert        | 200  | Achievement-Trigger              |
-- Formel: user.exp_points += event_exp; Level = MAX(level) WHERE exp_required <= user.exp_points

-- Badge-Definitionen-Katalog (formale Definition aller Achievements)
CREATE TABLE badge_definitions (
  badge_id        TEXT PRIMARY KEY,          -- z.B. "fog_clearer", "guild_contributor", "master_architect"
  title           TEXT NOT NULL,             -- Anzeigename: "Fog Clearer"
  description     TEXT NOT NULL,             -- "500 Code-Nodes im Nexus Grid erkundet"
  icon            TEXT,                      -- Icon-Reference oder Emoji (z.B. "🗺️", "🏗️", "⚔️")
  category        TEXT NOT NULL DEFAULT 'general', -- general|exploration|collaboration|quality
  unlock_condition TEXT NOT NULL,            -- Maschinenlesbare Bedingung: "code_nodes_explored >= 500"
  exp_reward      INT NOT NULL DEFAULT 0,   -- Bonus-EXP bei Freischaltung
  created_at      TIMESTAMPTZ DEFAULT now()
);
-- Bootstrap-Daten:
-- INSERT INTO badge_definitions VALUES
--   ('fog_clearer',       'Fog Clearer',       '500 Code-Nodes im Nexus Grid erkundet',             '🗺️', 'exploration',    'code_nodes_explored >= 500',          200),
--   ('guild_contributor', 'Guild Contributor', '10 eigene Skills von Peers übernommen',              '⚔️', 'collaboration',  'skills_forked_by_peers >= 10',        150),
--   ('master_architect',  'Master Architect',  '20 Epics erfolgreich (alle Tasks done) abgeschlossen','🏗️', 'quality',        'epics_completed >= 20',               300),
--   ('sla_savior',        'SLA Savior',        '10 Eskalationen innerhalb SLA gelöst',               '⏱️', 'quality',        'escalations_resolved_in_sla >= 10',   100),
--   ('first_blood',       'First Blood',       'Ersten Task abgeschlossen',                          '🎯', 'general',        'tasks_completed >= 1',                 25),
--   ('cartographer',      'Cartographer',      '1000 Code-Nodes kartiert',                           '🌍', 'exploration',    'code_nodes_explored >= 1000',         500),
--   ('skill_smith',       'Skill Smith',       '10 Skill-Proposals gemergt',                         '🔧', 'quality',        'skills_merged >= 10',                 200);

CREATE TABLE user_achievements (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  badge_id    TEXT NOT NULL REFERENCES badge_definitions(badge_id), -- FK auf badge_definitions statt freier Text
  earned_at   TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, badge_id)
);

-- ─────────────────────────────────────────────
-- EPICS & TASKS
-- ─────────────────────────────────────────────

CREATE SEQUENCE epic_key_seq;

CREATE TABLE epics (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  epic_key        TEXT NOT NULL UNIQUE,
  -- epic_key wird in der Applikationsschicht generiert:
  -- epic_key = f"EPIC-{nextval('epic_key_seq')}" (Python, vor INSERT)
  -- Analog zu task_key: API-stabil, immutable, menschenlesbar.
  project_id      UUID REFERENCES projects(id), -- NULL erlaubt für federated
  external_id     TEXT UNIQUE,
  title           TEXT NOT NULL,
  description     TEXT,
  owner_id        UUID REFERENCES users(id),    -- NULL erlaubt für federated
  backup_owner_id UUID REFERENCES users(id),
  state           TEXT NOT NULL DEFAULT 'incoming',
  priority        TEXT DEFAULT 'medium',
  -- priority-Werte (kanonisch): 'low' | 'medium' | 'high' | 'critical'
  -- NULL ist nicht erlaubt (DEFAULT 'medium'); konfigurierbar via Epic-Scoping-Modal.
  -- Validierung auf Applikationsebene; DB-Constraint als Sicherheitsnetz:
  CONSTRAINT chk_epic_priority CHECK (priority IN ('low', 'medium', 'high', 'critical')),
  sla_due_at      TIMESTAMPTZ,
  -- sla_due_at ist nullable. Verhalten bei NULL (kein SLA gesetzt):
  --   - Kein SLA-Timer in der UI (Anzeige: "∞" oder "Kein SLA")
  --   - SLA-Cron überspringt Epics mit sla_due_at IS NULL (kein Warning, keine Breach-Notification)
  --   - Epic erscheint nicht in SLA-nahen Priorisierungen der Prompt Queue
  --   - Empfehlung: SLA beim Scoping setzen; NULL als "unbefristet" interpretieren, nicht als Fehler
  dod_framework   JSONB,
  embedding       vector(768),   -- nomic-embed-text (Ollama, default); bei Wechsel auf OpenAI → ALTER auf 1536
  embedding_model TEXT,           -- Modell das dieses Embedding berechnet hat (Partial Recompute bei Provider-Wechsel)
  version         INT NOT NULL DEFAULT 0,
  -- Federation
  origin_node_id  UUID REFERENCES nodes(id), -- NULL = lokal erstellt; gesetzt = von Peer empfangen
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now(),
  CHECK (origin_node_id IS NOT NULL OR project_id IS NOT NULL),
  CHECK (origin_node_id IS NOT NULL OR owner_id IS NOT NULL)
);

-- epic_key bleibt API-stabil und immutable (EPIC-12 darf nicht umbenannt werden)
CREATE OR REPLACE FUNCTION prevent_epic_key_update()
RETURNS trigger AS $$
BEGIN
  IF NEW.epic_key IS DISTINCT FROM OLD.epic_key THEN
    RAISE EXCEPTION 'epic_key is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_epics_epic_key_immutable
BEFORE UPDATE ON epics
FOR EACH ROW
WHEN (OLD.epic_key IS DISTINCT FROM NEW.epic_key)
EXECUTE FUNCTION prevent_epic_key_update();

CREATE SEQUENCE task_key_seq;

CREATE TABLE tasks (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_key           TEXT NOT NULL UNIQUE,
  -- task_key wird in der Applikationsschicht generiert:
  -- task_key = f"TASK-{nextval('task_key_seq')}" (Python, vor INSERT)
  -- PostgreSQL DEFAULT unterstützt keine String-Konkatenation mit nextval().
  epic_id            UUID NOT NULL REFERENCES epics(id),
  parent_task_id     UUID REFERENCES tasks(id),
  title              TEXT NOT NULL,
  description        TEXT,
  state              TEXT NOT NULL DEFAULT 'incoming',
  -- state: incoming|scoped|ready|in_progress|in_review|done|qa_failed|blocked|escalated|cancelled
  version            INT NOT NULL DEFAULT 0,
  definition_of_done JSONB,
  quality_gate       JSONB,
  assigned_to        UUID REFERENCES users(id),
  assigned_node_id   UUID REFERENCES nodes(id), -- NULL = lokal; gesetzt = Sub-Task liegt bei Peer-Node
  pinned_skills      JSONB DEFAULT '[]', -- [{"skill_id": "uuid", "version": 2}]
  result             TEXT,               -- Worker-Ergebnis via submit_result
  artifacts          JSONB DEFAULT '[]', -- [{"type": "file", "path": "...", "description": "..."}]
  qa_failed_count    INT NOT NULL DEFAULT 0, -- Zähler für qa_failed-Transitionen; >= 3 → escalated
  review_comment     TEXT,               -- Owner-Kommentar bei qa_failed
  external_id        TEXT UNIQUE,
  created_at         TIMESTAMPTZ DEFAULT now(),
  updated_at         TIMESTAMPTZ DEFAULT now()
);

-- task_key bleibt API-stabil und immutable (TASK-88 darf nicht umbenannt werden)
CREATE OR REPLACE FUNCTION prevent_task_key_update()
RETURNS trigger AS $$
BEGIN
  IF NEW.task_key IS DISTINCT FROM OLD.task_key THEN
    RAISE EXCEPTION 'task_key is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tasks_task_key_immutable
BEFORE UPDATE ON tasks
FOR EACH ROW
WHEN (OLD.task_key IS DISTINCT FROM NEW.task_key)
EXECUTE FUNCTION prevent_task_key_update();

-- ─────────────────────────────────────────────
-- SKILLS
-- ─────────────────────────────────────────────

CREATE TABLE skills (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID REFERENCES projects(id), -- NULL = global oder federated
  title          TEXT NOT NULL,
  content        TEXT NOT NULL,
  service_scope  TEXT[] NOT NULL DEFAULT '{}',
  stack          TEXT[] NOT NULL DEFAULT '{}',
  version_range  JSONB,
  owner_id       UUID REFERENCES users(id),     -- NULL erlaubt für federated
  confidence     NUMERIC(3,2) DEFAULT 0.5,
  -- Confidence-Berechnung:
  --   Initial: 0.50 (Default bei Erstellung)
  --   Bei merge_skill (Gaertner-Proposal akzeptiert): keine Änderung (bleibt beim Start-Wert)
  --   Bei Task done + gepinnter Skill:       confidence += 0.05 (max 1.00)
  --   Bei Task qa_failed + gepinnter Skill:  confidence -= 0.10 (min 0.00)
  --   Bei accept_skill_change:               confidence += 0.02 (Verbesserung akkumuliert)
  --   Bei reject_skill_change:               keine Änderung (Proposal abgelehnt != Skill schlecht)
  --   Bei deprecated:                        confidence eingefroren (kein Update mehr)
  -- Update erfolgt atomar im approve_review / reject_review Handler (Backend).
  -- Manuelles Override: Admin kann confidence direkt setzen (für Kalibrierung).
  source_epics   TEXT[] DEFAULT '{}',
  skill_type        TEXT NOT NULL DEFAULT 'domain', -- system|domain
  -- skill_type: Unterscheidet Agent-Rollen-Skills ('system') von Fach-Skills ('domain').
  -- 'system': Agent-Rollen-Skills (z.B. hivemind-kartograph, hivemind-worker) — global, lifecycle-managed.
  --           Identifizierbar via skill_type='system' statt über project_id IS NULL (was auch für globale Fach-Skills gilt).
  -- 'domain': Fach-Skills die aus dem Gaertner-Flow entstehen (z.B. "FastAPI Endpoint erstellen").
  -- Validierung auf Applikationsebene; DB-Constraint als Sicherheitsnetz:
  CONSTRAINT chk_skill_type CHECK (skill_type IN ('system', 'domain')),
  lifecycle         TEXT NOT NULL DEFAULT 'draft', -- draft|pending_merge|active|rejected|deprecated
  version           INT NOT NULL DEFAULT 1,
  embedding         vector(768),   -- nomic-embed-text (Ollama, default)
  embedding_model   TEXT,           -- Modell das dieses Embedding berechnet hat (z.B. 'nomic-embed-text', 'text-embedding-3-small')
                                    -- NULL = noch nicht berechnet oder Legacy-Embedding ohne Tracking
                                    -- Ermöglicht Partial Recompute bei Provider-Wechsel: nur Zeilen mit altem Modell neu berechnen
  -- Federation
  origin_node_id    UUID REFERENCES nodes(id), -- NULL = lokal; gesetzt = von Peer empfangen
  federation_scope  TEXT NOT NULL DEFAULT 'local', -- local|federated (federated = wird an Peers gepusht)
  deleted_at        TIMESTAMPTZ,          -- Soft-Delete: gesetzt bei Peer-Entfernung/Offboarding; Eintrag bleibt für Audit lesbar, wiederherstellbar innerhalb 30 Tagen
  created_at        TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now(),
  CHECK (origin_node_id IS NOT NULL OR owner_id IS NOT NULL)
);

CREATE TABLE skill_versions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id        UUID NOT NULL REFERENCES skills(id),
  version         INT NOT NULL,
  content         TEXT NOT NULL,          -- vollständig assemblierter Inhalt (Parents aufgelöst)
  parent_versions JSONB DEFAULT '[]',     -- [{"skill_id": "uuid", "version": 3}] — Snapshot der Parent-Versionen
  token_count     INT,                    -- Token-Count des assemblierten Inhalts (tiktoken cl100k_base); beim Merge/Version-Update einmalig berechnet und gecacht
  changed_by      UUID NOT NULL REFERENCES users(id),
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(skill_id, version)               -- verhindert doppelte Versionen; Task-Pinning eindeutig
);

-- Skill Composition: Parent-Child-Beziehungen (extends)
CREATE TABLE skill_parents (
  child_id   UUID NOT NULL REFERENCES skills(id),
  parent_id  UUID NOT NULL REFERENCES skills(id),
  order_idx  INT NOT NULL DEFAULT 0,  -- Merge-Reihenfolge bei mehreren Parents
  PRIMARY KEY (child_id, parent_id),
  CHECK (child_id != parent_id)       -- kein Self-Reference
);

-- ─────────────────────────────────────────────
-- SKILL CHANGE PROPOSALS
-- ─────────────────────────────────────────────

-- Für propose_skill_change: diff + rationale werden hier gespeichert
-- Ein Skill kann mehrere offene Change-Proposals haben (aber nur einen aktiven Lifecycle-State)
-- Hinweis: guard_change_proposals steht nach guards (FK-Abhängigkeit)
CREATE TABLE skill_change_proposals (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_id     UUID NOT NULL REFERENCES skills(id),
  proposed_by  UUID NOT NULL REFERENCES users(id),
  diff         TEXT NOT NULL,      -- Unified diff oder Volltext-Vorschlag (Markdown)
  rationale    TEXT NOT NULL,      -- Begründung des Gaertners
  state        TEXT NOT NULL DEFAULT 'open', -- open|accepted|rejected
  reviewed_by  UUID REFERENCES users(id),
  reviewed_at  TIMESTAMPTZ,
  review_note  TEXT,               -- Admin-Begründung bei Ablehnung
  version      INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- DOCS & CONTEXT
-- ─────────────────────────────────────────────

-- Docs sind immer Epic-gebunden (kein eigenständiger project_id).
-- Projektweites Wissen ohne Epic-Bezug gehört ins Wiki (→ wiki_articles).
-- epic_id ist nullable für den Sonderfall von Entwurfs-Docs die noch keinem Epic zugeordnet sind.
CREATE TABLE docs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title       TEXT NOT NULL,
  content     TEXT NOT NULL,
  epic_id     UUID REFERENCES epics(id),
  embedding   vector(768),   -- nomic-embed-text (Ollama, default)
  embedding_model TEXT,       -- Modell das dieses Embedding berechnet hat (Partial Recompute bei Provider-Wechsel)
  version     INT NOT NULL DEFAULT 0,
  updated_by  UUID REFERENCES users(id),
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE context_boundaries (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id          UUID NOT NULL UNIQUE REFERENCES tasks(id),
  allowed_skills   UUID[] DEFAULT '{}',
  allowed_docs     UUID[] DEFAULT '{}',
  external_access  TEXT[] DEFAULT '{}',  -- z.B. ["sentry"] für externe Services
  max_token_budget INT DEFAULT 8000,
  version          INT NOT NULL DEFAULT 0,
  set_by           UUID NOT NULL REFERENCES users(id),
  created_at       TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- WIKI
-- ─────────────────────────────────────────────

CREATE TABLE wiki_categories (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id   UUID REFERENCES wiki_categories(id), -- NULL = Top-Level-Kategorie
  title       TEXT NOT NULL,
  slug        TEXT NOT NULL UNIQUE,                 -- URL-Teil (z.B. "fastapi", "authentication", "jwt")
  sort_order  INT NOT NULL DEFAULT 0,
  created_at  TIMESTAMPTZ DEFAULT now()
);
-- Breadcrumb-Auflösung: Rekursive CTE über parent_id bis parent_id IS NULL.
-- Beispiel: JWT (parent: Authentication) → Authentication (parent: FastAPI) → FastAPI (parent: NULL)
-- Ergibt Breadcrumb: FastAPI > Authentication > JWT

CREATE TABLE wiki_articles (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id   UUID REFERENCES wiki_categories(id), -- NULL = unkategorisiert; Breadcrumb über wiki_categories.parent_id
  title         TEXT NOT NULL,
  slug          TEXT NOT NULL UNIQUE,
  content       TEXT NOT NULL,
  tags          TEXT[] NOT NULL DEFAULT '{}',
  linked_epics  UUID[] DEFAULT '{}',
  linked_skills UUID[] DEFAULT '{}',
  author_id         UUID REFERENCES users(id),    -- NULL erlaubt für federated
  embedding         vector(768),   -- nomic-embed-text (Ollama, default)
  embedding_model   TEXT,           -- Modell das dieses Embedding berechnet hat (Partial Recompute bei Provider-Wechsel)
  version           INT NOT NULL DEFAULT 1,
  -- Federation
  origin_node_id    UUID REFERENCES nodes(id), -- NULL = lokal; gesetzt = von Peer empfangen
  federation_scope  TEXT NOT NULL DEFAULT 'local', -- local|federated
  deleted_at        TIMESTAMPTZ,          -- Soft-Delete: gesetzt bei Peer-Entfernung/Offboarding; Eintrag bleibt für Audit lesbar, wiederherstellbar innerhalb 30 Tagen
  created_at        TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now(),
  CHECK (origin_node_id IS NOT NULL OR author_id IS NOT NULL)
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

-- ─────────────────────────────────────────────
-- NEXUS GRID (Code-Kartographie)
-- ─────────────────────────────────────────────

CREATE TABLE code_nodes (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID REFERENCES projects(id),   -- NULL erlaubt für federated
  path        TEXT NOT NULL,
  node_type   TEXT NOT NULL, -- file|module|package|service
  label       TEXT NOT NULL,
  explored_at TIMESTAMPTZ,   -- NULL = Fog of War
  explored_by UUID REFERENCES users(id),
  embedding   vector(768),   -- nomic-embed-text (Ollama, default)
  embedding_model TEXT,       -- Modell das dieses Embedding berechnet hat (Partial Recompute bei Provider-Wechsel)
  metadata    JSONB,
  -- Federation
  origin_node_id   UUID REFERENCES nodes(id), -- NULL = lokal entdeckt; gesetzt = von Peer empfangen
  federation_scope TEXT NOT NULL DEFAULT 'federated', -- Kartograph-Discoveries sind default federated
  exploring_node_id UUID REFERENCES nodes(id), -- temporär: welche Node erkundet gerade diese Area? NULL nach Abschluss
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE(project_id, path),
  CHECK (origin_node_id IS NOT NULL OR project_id IS NOT NULL)
);

CREATE TABLE code_edges (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id     UUID REFERENCES projects(id), -- Quell-Projekt; NULL erlaubt für federated
  source_id      UUID NOT NULL REFERENCES code_nodes(id),
  target_id      UUID NOT NULL REFERENCES code_nodes(id), -- kann in anderem Projekt liegen (cross-project Edge)
  edge_type      TEXT NOT NULL, -- import|call|dependency|extends
  -- Federation
  origin_node_id UUID REFERENCES nodes(id), -- NULL = lokal; gesetzt = von Peer empfangen
  created_at     TIMESTAMPTZ DEFAULT now(),
  UNIQUE(source_id, target_id, edge_type), -- ohne project_id: cross-project Edges eindeutig über source+target+type
  CHECK (origin_node_id IS NOT NULL OR project_id IS NOT NULL)
);
-- Cross-project Edge (Monorepo-Beispiel): Frontend-Code importiert UI-Controls aus anderem Projekt
--   project_id = frontend-project-uuid   (Quell-Projekt)
--   source_id  = code_node "src/Button.tsx" (in frontend-project)
--   target_id  = code_node "src/ui/Button.vue" (in ui-controls-project)
--   edge_type  = 'import'

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

-- ─────────────────────────────────────────────
-- PROMPT HISTORY
-- ─────────────────────────────────────────────

-- Persistiert generierte Prompts für den Prompt-Verlauf (Phase 4 Feature: "Kollabierbare History")
CREATE TABLE prompt_history (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id   UUID REFERENCES projects(id),
  epic_id      UUID REFERENCES epics(id),
  task_id      UUID REFERENCES tasks(id),
  agent_type   TEXT NOT NULL,  -- kartograph|stratege|architekt|bibliothekar|worker|gaertner|triage
  prompt_type  TEXT NOT NULL,  -- get_prompt type: kartograph|stratege|architekt|bibliothekar|worker|gaertner|triage|review
  prompt_text   TEXT NOT NULL,  -- Vollständig assemblierter Prompt-Text
  override_text TEXT,           -- Vom User angepasster Prompt-Text (gesetzt via POST /api/prompts/:id/override); NULL = kein Override aktiv; überschreibt prompt_text für diesen Queue-Eintrag
  token_count   INT,            -- Token-Count des assemblierten Prompts
  generated_by  UUID REFERENCES users(id), -- User der den Prompt angefordert hat
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- AUDIT & MCP
-- ─────────────────────────────────────────────

CREATE TABLE mcp_invocations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id      UUID NOT NULL,
  idempotency_key UUID UNIQUE,
  actor_id        UUID NOT NULL REFERENCES users(id),
  actor_role      TEXT NOT NULL, -- developer|admin|service|kartograph
  tool_name       TEXT NOT NULL,
  epic_id         UUID,
  target_id       TEXT,
  input_payload   JSONB,
  output_payload  JSONB,
  status          TEXT NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- IDEMPOTENZ (Write-Deduplication)
-- ─────────────────────────────────────────────

-- Speichert verwendete Idempotency-Keys mit gecachter Response.
-- Verarbeitungsablauf:
--   1. Client sendet Write-Request mit `Idempotency-Key: <UUID>` Header
--   2. Backend prüft idempotency_keys WHERE key = <UUID>
--      a) Key existiert + status='completed': gecachte Response zurückgeben (HTTP 200, kein erneuter Write)
--      b) Key existiert + status='processing': HTTP 409 Conflict ("Request wird gerade verarbeitet")
--      c) Key existiert nicht: INSERT mit status='processing', dann Write ausführen, dann UPDATE auf 'completed'
--   3. Bei fehlgeschlagenem Write: Key-Eintrag löschen (Client kann Retry mit gleichem Key)
-- TTL: 24 Stunden. Täglicher Cleanup-Job löscht abgelaufene Keys.
-- Kein Redis nötig in Phase 1–7 — PostgreSQL-basiert (ausreichend für Single-Instance).
CREATE TABLE idempotency_keys (
  key             UUID PRIMARY KEY,
  actor_id        UUID NOT NULL REFERENCES users(id),
  tool_name       TEXT NOT NULL,           -- MCP-Tool oder REST-Endpoint
  status          TEXT NOT NULL DEFAULT 'processing', -- processing|completed
  response_status INT,                     -- HTTP-Status der gecachten Response
  response_body   JSONB,                   -- Gecachte Response (komplett)
  created_at      TIMESTAMPTZ DEFAULT now(),
  expires_at      TIMESTAMPTZ DEFAULT now() + interval '24 hours'
);

-- Partial-Index für Cleanup-Job: nur abgelaufene Keys
CREATE INDEX idx_idempotency_keys_expires ON idempotency_keys(expires_at) WHERE status = 'completed';

-- ─────────────────────────────────────────────
-- SYNC: Outbox & Dead Letter Queue
-- ─────────────────────────────────────────────

CREATE TABLE sync_outbox (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dedup_key     TEXT UNIQUE,          -- Idempotenz je externes Ereignis (z.B. "youtrack:event:1718036400:ISSUE-42")
  direction     TEXT NOT NULL DEFAULT 'inbound', -- inbound|outbound|peer_outbound|peer_inbound
  system        TEXT NOT NULL,        -- "youtrack" | "sentry" | "federation"
  target_node_id UUID REFERENCES nodes(id), -- gesetzt bei direction='peer_outbound': welcher Peer ist Ziel?
  entity_type   TEXT NOT NULL,
  entity_id     TEXT NOT NULL,
  payload       JSONB NOT NULL,
  attempts      INT NOT NULL DEFAULT 0,
  next_retry_at TIMESTAMPTZ,
  state         TEXT NOT NULL DEFAULT 'pending', -- pending|processing|done|dead|cancelled|quarantined
  -- quarantined: verdächtige Einträge nach Key-Kompromittierung (Federation Emergency, → federation.md)
  routing_state TEXT DEFAULT 'unrouted',         -- unrouted|routed|ignored — für Triage-Anzeige
  -- unrouted: wartet auf manuelle Entscheidung in Triage Station
  -- routed:   wurde einem Epic zugewiesen (manuell oder auto)
  -- ignored:  Admin hat bewusst entschieden, Event nicht zu routen (kein Epic-Bezug); bleibt lesbar für Audit
  embedding       vector(768),   -- nomic-embed-text (Ollama, default); für pgvector-basiertes Auto-Routing ungerouteter Events
  embedding_model TEXT,           -- Modell das dieses Embedding berechnet hat (Partial Recompute bei Provider-Wechsel)
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sync_dead_letter (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  outbox_id     UUID NOT NULL REFERENCES sync_outbox(id),
  system        TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  entity_id     TEXT NOT NULL,
  payload       JSONB NOT NULL,
  error         TEXT,
  failed_at     TIMESTAMPTZ DEFAULT now(),
  requeued_by   UUID REFERENCES users(id),
  requeued_at   TIMESTAMPTZ,
  discarded_by  UUID REFERENCES users(id),    -- gesetzt bei discard_dead_letter
  discarded_at  TIMESTAMPTZ                   -- gesetzt bei discard_dead_letter; Eintrag bleibt für Audit
);

-- ─────────────────────────────────────────────
-- DECISIONS
-- ─────────────────────────────────────────────

CREATE TABLE decision_requests (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id         UUID NOT NULL REFERENCES tasks(id),
  epic_id         UUID NOT NULL REFERENCES epics(id),
  owner_id        UUID NOT NULL REFERENCES users(id),
  backup_owner_id UUID REFERENCES users(id),
  state           TEXT NOT NULL DEFAULT 'open', -- open|resolved|expired
  sla_due_at      TIMESTAMPTZ NOT NULL,
  version         INT NOT NULL DEFAULT 0,
  resolved_by     UUID REFERENCES users(id),
  resolved_at     TIMESTAMPTZ,
  payload         JSONB NOT NULL
  -- payload: { blocker, options: [{id, description, tradeoffs}] }
);

CREATE TABLE decision_records (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  epic_id             UUID NOT NULL REFERENCES epics(id),
  decision_request_id UUID REFERENCES decision_requests(id),
  decision            TEXT NOT NULL,
  rationale           TEXT,
  decided_by          UUID NOT NULL REFERENCES users(id),
  created_at          TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- EPIC PROPOSALS (Stratege)
-- ─────────────────────────────────────────────

-- Epic-Proposals des Strategen. Abgeleitet aus Plan-Dokumenten.
-- Werden in der Triage Station als [EPIC PROPOSAL] angezeigt.
CREATE TABLE epic_proposals (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id          UUID NOT NULL REFERENCES projects(id),
  proposed_by         UUID NOT NULL REFERENCES users(id),
  title               TEXT NOT NULL,
  description         TEXT NOT NULL,          -- Markdown: Was soll dieses Epic leisten?
  rationale           TEXT NOT NULL,          -- Begründung: Aus welchem Plan-Abschnitt abgeleitet?
  suggested_priority  TEXT DEFAULT 'medium',  -- critical|high|medium|low
  suggested_phase     INT,                    -- Optionale Phasen-Zuordnung
  depends_on          UUID[] DEFAULT '{}',    -- Referenzen auf andere epic_proposals.id oder epics.id
  suggested_owner_id  UUID REFERENCES users(id), -- Empfohlener Epic-Owner
  state               TEXT NOT NULL DEFAULT 'proposed', -- proposed|accepted|rejected
  -- proposed:  Stratege hat vorgeschlagen, wartet auf Triage-Review
  -- accepted: Admin/Owner hat akzeptiert → Epic (incoming) wird erstellt
  -- rejected: Admin/Owner hat abgelehnt mit Begründung
  resulting_epic_id   UUID REFERENCES epics(id), -- Gesetzt wenn accepted → verweist auf das erstellte Epic
  reviewed_by         UUID REFERENCES users(id),
  review_reason       TEXT,                   -- Begründung bei Ablehnung
  reviewed_at         TIMESTAMPTZ,
  version             INT NOT NULL DEFAULT 0,
  created_at          TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- EPIC RESTRUCTURE PROPOSALS (Kartograph)
-- ─────────────────────────────────────────────

CREATE TABLE epic_restructure_proposals (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  epic_id     UUID NOT NULL REFERENCES epics(id),
  proposed_by UUID NOT NULL REFERENCES users(id),  -- immer ein User mit kartograph-Rolle (nicht service-Rolle)
  rationale   TEXT NOT NULL,
  proposal    TEXT NOT NULL,          -- Freitext-Vorschlag des Kartographen (Markdown)
  state       TEXT NOT NULL DEFAULT 'open', -- open|accepted|rejected
  version     INT NOT NULL DEFAULT 0,
  -- Admin: accept_epic_restructure → accepted; reject_epic_restructure → rejected
  reviewed_by UUID REFERENCES users(id),
  reviewed_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- GUARDS (Executable Validierungsregeln)
-- ─────────────────────────────────────────────

CREATE TABLE guards (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID REFERENCES projects(id),  -- NULL = global
  skill_id    UUID REFERENCES skills(id),     -- NULL = nicht skill-spezifisch
  title       TEXT NOT NULL,
  description TEXT,
  type        TEXT NOT NULL DEFAULT 'executable', -- executable|declarative|manual
  command     TEXT,          -- für executable: "pytest --cov-fail-under=80"
  condition   TEXT,          -- für declarative: maschinenlesbare Bedingung
  scope       TEXT[] DEFAULT '{}',  -- ["backend", "frontend"] — leer = alle
  lifecycle   TEXT NOT NULL DEFAULT 'draft', -- draft|pending_merge|active|rejected|deprecated
  skippable   BOOLEAN NOT NULL DEFAULT true, -- false = Worker kann nur passed/failed melden, kein skip
  version     INT NOT NULL DEFAULT 0,
  created_by  UUID NOT NULL REFERENCES users(id),
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE task_guards (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id    UUID NOT NULL REFERENCES tasks(id),
  guard_id   UUID NOT NULL REFERENCES guards(id),
  status     TEXT NOT NULL DEFAULT 'pending', -- pending|passed|failed|skipped
  result     TEXT,                             -- Output des executable Guards
  checked_at TIMESTAMPTZ,
  checked_by UUID REFERENCES users(id),        -- NULL = automatisch
  UNIQUE(task_id, guard_id)
);

-- ─────────────────────────────────────────────
-- GUARD CHANGE PROPOSALS
-- ─────────────────────────────────────────────

-- Steht nach guards (FK-Abhängigkeit auf guards.id)
-- Für propose_guard_change: diff + rationale werden hier gespeichert
CREATE TABLE guard_change_proposals (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  guard_id     UUID NOT NULL REFERENCES guards(id),
  proposed_by  UUID NOT NULL REFERENCES users(id),
  diff         TEXT NOT NULL,      -- Unified diff oder Volltext-Vorschlag (Markdown)
  rationale    TEXT NOT NULL,      -- Begründung des Kartographen
  state        TEXT NOT NULL DEFAULT 'open', -- open|accepted|rejected
  reviewed_by  UUID REFERENCES users(id),
  reviewed_at  TIMESTAMPTZ,
  review_note  TEXT,               -- Admin-Begründung bei Ablehnung
  version      INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────────
-- NOTIFICATIONS (In-App, kein externer Service)
-- ─────────────────────────────────────────────

CREATE TABLE notifications (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(id),
  type       TEXT NOT NULL,
  -- Typen (kanonisch, übereinstimmend mit phase-6.md Routing-Matrix):
  --   sla_warning                 — SLA-Deadline nähert sich (4h vor Fälligkeit) → Owner
  --   sla_breach                  — SLA überschritten → Backup-Owner
  --   decision_request            — Worker hat Decision Request erstellt → Owner
  --   decision_escalated_backup   — 48h ohne Auflösung → Backup-Owner
  --   decision_escalated_admin    — 72h ohne Auflösung → alle Admins
  --   escalation                  — Task nach 3x qa_failed eskaliert → Owner + Admins
  --   skill_proposal              — Gaertner hat Skill-Proposal eingereicht → alle Admins
  --   skill_merged                — Skill wurde gemergt → Skill-Proposer + Admins
  --   task_done                   — Task wurde auf done gesetzt → Assignee + Owner
  --   dead_letter                 — Sync in DLQ gelandet → alle Admins
  --   guard_failed                — Guard fehlgeschlagen → Assigned-Worker + Owner
  --   task_assigned               — Task einem User zugewiesen → neuer Assignee
  --   review_requested            — Task geht in in_review → Owner
  --   task_delegated              — Task wurde an Peer-Node delegiert → Epic-Owner (Phase F)
  --   peer_offline                — Peer mit delegierten Tasks nicht erreichbar → alle Admins (Phase F)
  --   guard_proposal              — Neuer Guard-Proposal eingereicht → alle Admins
  --   restructure_proposal        — Kartograph schlägt Epic-Restructure vor → alle Admins
  --   peer_task_done              — Peer hat delegierten Task abgeschlossen → Epic-Owner (Phase F)
  --   peer_online                 — Peer-Node ist wieder erreichbar → alle User (Phase F)
  --   federated_skill             — Neuer Skill von Peer-Node verfügbar → alle User (Phase F)
  --   discovery_session           — Peer erkundet Codebase-Area → alle User (Phase F)
  --   restructure_rejected        — Epic-Restructure-Proposal wurde abgelehnt → Kartograph/Proposer
  priority   TEXT NOT NULL DEFAULT 'fyi',
  -- Priority-Gruppen (kanonisch, übereinstimmend mit views.md Notification-Tray):
  --   action_now  — sofortige Aufmerksamkeit erforderlich
  --   action_soon — zeitnah, aber nicht sofort
  --   fyi         — informativ, kein Handlungsbedarf
  -- Mapping type → priority:
  --   action_now:  sla_breach, escalation, decision_escalated_admin, dead_letter, peer_offline
  --   action_soon: sla_warning, decision_request, decision_escalated_backup, guard_failed,
  --                review_requested, task_delegated, guard_proposal, restructure_proposal
  --   fyi:         skill_proposal, skill_merged, task_done, task_assigned, peer_task_done,
  --                peer_online, federated_skill, discovery_session, restructure_rejected
  title      TEXT NOT NULL,
  body       TEXT,
  link       TEXT,           -- Deep-Link z.B. /epics/uuid
  read       BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Notification-Retention: gelesene Notifications werden nach NOTIFICATION_RETENTION_DAYS (default: 90) gelöscht.
-- Ungelesene Notifications werden nach NOTIFICATION_UNREAD_RETENTION_DAYS (default: 365) gelöscht.
-- Der Retention-Cron läuft täglich (zusammen mit dem Audit-Retention-Cron).
-- DELETE FROM notifications WHERE (read = true AND created_at < now() - interval 'NOTIFICATION_RETENTION_DAYS days')
--    OR (read = false AND created_at < now() - interval 'NOTIFICATION_UNREAD_RETENTION_DAYS days');
```

---

## Indexes

Performance-kritische Indexes (werden in der initialen Migration angelegt):

```sql
-- Tasks: häufige State-Queries
CREATE INDEX idx_tasks_state       ON tasks(state);
CREATE INDEX idx_tasks_epic_id     ON tasks(epic_id);
CREATE INDEX idx_tasks_assigned_to ON tasks(assigned_to);

-- Epics: SLA-Cron + Routing
CREATE INDEX idx_epics_state      ON epics(state);
CREATE INDEX idx_epics_project_id ON epics(project_id);
CREATE INDEX idx_epics_owner_id   ON epics(owner_id);
CREATE INDEX idx_epics_epic_key   ON epics(epic_key);
-- Partial-Index für SLA-Cron: nur aktive Epics mit gesetztem SLA-Datum
CREATE INDEX idx_epics_sla_due ON epics(sla_due_at)
  WHERE state NOT IN ('done', 'cancelled') AND sla_due_at IS NOT NULL;

-- Skills: Bibliothekar-Suche
CREATE INDEX idx_skills_lifecycle ON skills(lifecycle);
CREATE INDEX idx_skills_project_id ON skills(project_id);

-- pgvector: HNSW-Index für Cosine-Similarity (ab Phase 3 befüllt)
-- Index-Typ: HNSW (Hierarchical Navigable Small World) — gewählt wegen:
--   (a) Bessere Query-Performance als IVFFlat bei < 1M Vektoren
--   (b) Kein Rebuild nach Inserts nötig (IVFFlat braucht regelmäßiges REINDEX)
--   (c) INSERT-Performance akzeptabel für Hivemind-Workload (kein Massen-Streaming)
-- Parameter (Defaults, anpassbar via ALTER INDEX ... SET):
--   ef_construction = 64  — Qualität beim Index-Aufbau (höher = genauer, langsamer)
--   m = 16                — Max. Kanten pro Node im Graph (höher = mehr RAM, bessere Recall)
-- Query-Parameter (Session-Level, pro Query anpassbar):
--   SET hnsw.ef_search = 40;  — Suchtiefe (höher = genauer, langsamer; Default: 40)
-- Skalierungs-Richtwerte:
--   < 10.000 Embeddings:  Defaults ausreichend (< 10ms Query-Zeit)
--   10.000 – 100.000:     ef_search = 100, ef_construction = 128 evaluieren
--   > 100.000:            ef_construction = 200, m = 32; Monitoring via pg_stat_user_indexes
-- Rebuild-Strategie nach Massen-Imports (z.B. Kartograph-Bootstrap > 1000 Nodes):
--   REINDEX INDEX CONCURRENTLY idx_code_nodes_embedding;  — kein Downtime, kein Lock
--   Empfehlung: Batch-Import → REINDEX CONCURRENTLY → dann Queries (bessere Recall nach Rebuild)
CREATE INDEX idx_epics_embedding        ON epics    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_skills_embedding       ON skills   USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_wiki_articles_embedding ON wiki_articles USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_docs_embedding         ON docs         USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_code_nodes_embedding   ON code_nodes USING hnsw (embedding vector_cosine_ops);

-- pgvector: Sync-Outbox Embedding für Auto-Routing ungerouteter Events
CREATE INDEX idx_sync_outbox_embedding  ON sync_outbox USING hnsw (embedding vector_cosine_ops);

-- Sync: Outbox-Queue-Processing
CREATE INDEX idx_sync_outbox_state         ON sync_outbox(state);
CREATE INDEX idx_sync_outbox_routing_state ON sync_outbox(routing_state);
CREATE INDEX idx_sync_outbox_next_retry    ON sync_outbox(next_retry_at) WHERE state = 'pending';
CREATE INDEX idx_sync_outbox_direction_state ON sync_outbox(direction, state);

-- Notifications: Ungelesene Notifications per User
CREATE INDEX idx_notifications_user_unread ON notifications(user_id) WHERE read = false;

-- Skill/Guard Change Proposals: Admin-Review-Queue
CREATE INDEX idx_skill_change_proposals_state    ON skill_change_proposals(state);
CREATE INDEX idx_skill_change_proposals_skill_id ON skill_change_proposals(skill_id);
CREATE INDEX idx_guard_change_proposals_state    ON guard_change_proposals(state);
CREATE INDEX idx_guard_change_proposals_guard_id ON guard_change_proposals(guard_id);

-- Guards: Scope-basierte Abfragen
CREATE INDEX idx_guards_lifecycle  ON guards(lifecycle);
CREATE INDEX idx_guards_project_id ON guards(project_id);

-- Audit: Filtering
CREATE INDEX idx_mcp_invocations_actor_id  ON mcp_invocations(actor_id);
CREATE INDEX idx_mcp_invocations_tool_name ON mcp_invocations(tool_name);
CREATE INDEX idx_mcp_invocations_epic_id   ON mcp_invocations(epic_id);
CREATE INDEX idx_mcp_invocations_created   ON mcp_invocations(created_at DESC);

-- Decision Requests: SLA-Cron + Triage-Abfragen
CREATE INDEX idx_decision_requests_task_id ON decision_requests(task_id);
CREATE INDEX idx_decision_requests_state   ON decision_requests(state);
CREATE INDEX idx_decision_requests_sla_due ON decision_requests(sla_due_at);

-- Decision Requests: höchstens 1 offener DR pro Task (DB-seitig erzwungen)
CREATE UNIQUE INDEX idx_decision_requests_one_open_per_task ON decision_requests(task_id) WHERE state = 'open';

-- Federation: Peer-Routing und Origin-Tracking
CREATE INDEX idx_epics_origin_node_id         ON epics(origin_node_id) WHERE origin_node_id IS NOT NULL;
CREATE INDEX idx_tasks_assigned_node_id       ON tasks(assigned_node_id) WHERE assigned_node_id IS NOT NULL;
CREATE INDEX idx_skills_origin_node_id        ON skills(origin_node_id) WHERE origin_node_id IS NOT NULL;
CREATE INDEX idx_skills_federation_scope      ON skills(federation_scope);
CREATE INDEX idx_wiki_articles_origin_node_id ON wiki_articles(origin_node_id) WHERE origin_node_id IS NOT NULL;
CREATE INDEX idx_sync_outbox_target_node_id      ON sync_outbox(target_node_id) WHERE target_node_id IS NOT NULL;
CREATE INDEX idx_nodes_status                    ON nodes(status);
CREATE INDEX idx_code_nodes_origin_node_id       ON code_nodes(origin_node_id) WHERE origin_node_id IS NOT NULL;
CREATE INDEX idx_code_nodes_exploring_node_id    ON code_nodes(exploring_node_id) WHERE exploring_node_id IS NOT NULL;
CREATE INDEX idx_code_edges_project_id           ON code_edges(project_id);
CREATE INDEX idx_code_edges_target_id            ON code_edges(target_id); -- cross-project: "wer hängt von diesem Node ab?"
CREATE INDEX idx_code_edges_origin_node_id       ON code_edges(origin_node_id) WHERE origin_node_id IS NOT NULL;

-- Wiki-Categories: Breadcrumb-Auflösung
CREATE INDEX idx_wiki_categories_parent_id ON wiki_categories(parent_id);

-- Wiki-Articles: Kategorie-Zuordnung
CREATE INDEX idx_wiki_articles_category_id ON wiki_articles(category_id) WHERE category_id IS NOT NULL;

-- Prompt History: Verlaufs-Queries
CREATE INDEX idx_prompt_history_project_id ON prompt_history(project_id);
CREATE INDEX idx_prompt_history_task_id    ON prompt_history(task_id);
CREATE INDEX idx_prompt_history_created    ON prompt_history(created_at DESC);
```

> HNSW-Indexes für pgvector sind beim ersten `CREATE INDEX` leer und werden mit den Embeddings befüllt. In Phase 1–2 noch nicht genutzt, aber Schema ist bereit.

> **Embedding-Dimension (768):** Basiert auf dem Default-Provider `nomic-embed-text` (Ollama). Bei Wechsel auf OpenAI `text-embedding-3-small` (1536 Dims) müssen die Embedding-Spalten per `ALTER TABLE ... ALTER COLUMN embedding TYPE vector(1536)` angepasst und alle Embeddings neu berechnet werden. Kein Datenverlust — Embeddings werden ohnehin vom Provider-Switch-Job neu erzeugt (→ [bibliothekar.md](../agents/bibliothekar.md)).

> **HNSW-Skalierung:** Bei > 10.000 Nodes kann ein Re-Indexing-Job mehrere Minuten dauern. HNSW-Indexes unterstützen `CREATE INDEX CONCURRENTLY` — Re-Indexing im Live-Betrieb ohne Downtime möglich. Ab > 100.000 Embeddings sollte `ef_construction` und `m` angepasst werden (Default: `ef_construction=64, m=16`). Monitoring via `pg_stat_user_indexes`.

---

## JSONB-Schemas

**definition_of_done:**

```json
{
  "criteria": [
    { "id": "c1", "description": "Unit tests >= 80% Coverage", "required": true },
    { "id": "c2", "description": "API-Dokumentation aktualisiert", "required": false }
  ],
  "checklist_mode": "all_required"
}
```

**pinned_skills (auf tasks):**

```json
[
  { "skill_id": "uuid", "version": 2 },
  { "skill_id": "uuid", "version": 1 }
]
```

> **Designentscheidung — kein FK für pinned_skills:** `pinned_skills` ist JSONB statt einer separaten Join-Tabelle. Das ermöglicht Versions-Snapshots ohne DB-Constraint-Komplexität. Da `skill_versions` immutable (append-only) ist, ist Referential Integrity de-facto gegeben. Konsistenz wird auf Applikationsebene sichergestellt: `skill_id` muss existieren und die Version muss zum Pinning-Zeitpunkt `active` gewesen sein.

---

## Designentscheidung: UUID-FK intern, task_key/epic_key API-stabil

MCP-Tools und Prompts verwenden weiterhin `task_key` (z.B. `"TASK-88"`) und `epic_key` (z.B. `"EPIC-12"`).  
Intern löst das Backend den Key einmal auf `tasks.id` bzw. `epics.id` (UUID) auf und arbeitet danach nur mit UUID-FKs.

| Entscheidung | Wirkung |
| --- | --- |
| `context_boundaries.task_id` und `decision_requests.task_id` als UUID-FK | Keine Orphan-Einträge, referentielle Integrität durch DB |
| `task_key` und `epic_key` bleiben API-Identifier | Keine Änderung für MCP-Clients/Prompts |
| `task_key` und `epic_key` sind immutable (DB-Trigger) | Stabile externe Referenzen, kein späteres Renaming-Risiko |

> Die zusätzliche Key→UUID-Auflösung ist ein einfacher, indexierter Lookup auf `tasks.task_key` bzw. `epics.epic_key` und steht im Verhältnis zum Integritätsgewinn.

---

## Audit-Retention

- **Volle Payload (input + output):** 90 Tage (`AUDIT_RETENTION_DAYS`)
- **Summary (actor, tool, timestamp, status, epic_id):** 1 Jahr
- **Keine Löschung** — nach Ablauf wird `input_payload`/`output_payload` auf `null` gesetzt, Record bleibt
- Täglicher Archivierungs-Job im Backend
