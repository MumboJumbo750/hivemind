# Phase 8 — Volle Autonomie

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** AI-Client konsumiert Prompts direkt via API-Key. GitLab + GitHub Integration. MCP Bridge / Gateway (Meta-MCP). 3D Nexus Grid. **Conductor-Orchestrator, Reviewer-Agent, Governance-Levels.** Kein Architekturbruch.

**AI-Integration:** Per-Agent-Rolle konfigurierbare AI-Provider (→ `ai_provider_configs`-Tabelle). Jede Rolle (Kartograph, Stratege, Architekt, Worker, Gaertner, Triage) kann einen eigenen Provider + Modell + Endpoint nutzen — Cloud-APIs, Self-Hosted Ollama, GitHub Models, oder gemischt. Nicht-konfigurierte Rollen fallen auf den Global-Default oder BYOAI zurück.

**MCP-Gateway:** Hivemind wird zum **Meta-MCP** — gleichzeitig MCP-Server (für Agents) und MCP-Client (zu externen MCP-Servern wie GitHub MCP, GitLab MCP). Agents erhalten Tools aus allen Quellen über eine einzige Schnittstelle mit zentralem RBAC, Audit und Rate-Limiting.

**Voraussetzung:** Alle Kriterien aus [Definition of Ready](./overview.md#definition-of-ready-für-phase-8-autonomous-mode) erfüllt.

---

## Deliverables

### Backend
- [ ] AI-Provider-Service: sendet generierte Prompts direkt an AI-APIs
  - Provider-Abstraktion: `anthropic`, `openai`, `google`, `ollama` (lokal), `github_models` (GitHub Models API), `custom` (beliebiger OpenAI-kompatibler Endpoint)
  - **Per-Agent-Rolle konfigurierbar** via `ai_provider_configs`-Tabelle (→ [Bibliothekar — Agent-Provider-Routing](../agents/bibliothekar.md#agent-provider-routing), [data-model.md](../architecture/data-model.md))
  - Routing-Logik: Prompt-Typ → Agent-Rolle → Lookup `ai_provider_configs` → Provider-spezifischer Client
  - Fallback-Kaskade: `ai_provider_configs[rolle]` → `app_settings.ai_provider` (Global) → BYOAI-Modus
  - Gleicher Prompt wie bisher — kein Unterschied für MCP-Tools
  - **Rate-Limiting & Retry:**
    - Retry: Exponential Backoff (1s → 2s → 4s → max 60s), max 3 Versuche bei 429/503
    - RPM/TPM-Konfiguration: `HIVEMIND_AI_RPM_LIMIT` (Requests per Minute), `HIVEMIND_AI_TPM_LIMIT` (Tokens per Minute)
    - Bei Überschreitung: Queue-Eintrag bleibt `agent_required`, Prompt Station zeigt `RATE LIMITED — Retry in Xs`
    - Kein Circuit Breaker für AI-Provider (Retries sind ausreichend bei externem API)
  - **Dev-Umgebung Hinweis:** API-Keys werden via HTTPS übertragen. In Dev-Deployments ohne valides TLS-Zertifikat (self-signed oder HTTP) fließen Keys im Klartext. Empfehlung: API-Keys in Dev immer als Env-Var setzen (nicht via UI eingeben) und `HIVEMIND_ENFORCE_TLS=true` bei allen Deployments mit echtem Key.
  - **Env-Var-Fallback (Global):** `HIVEMIND_AI_API_KEY` als einzelner Global-Default. Per-Role-Keys werden über die UI oder direkt in der DB gesetzt.
- [ ] GitLab MCP Consumer: GitLab als Datenquelle (MRs, Pipelines, Issues)
  - **Auth:** Personal Access Token (PAT) via `HIVEMIND_GITLAB_TOKEN` Env-Var oder verschlüsselt in `app_settings` (selbes AES-256-GCM wie AI-Key)
  - **GitLab-URL:** `HIVEMIND_GITLAB_URL` (self-hosted oder gitlab.com)
  - **Ingest-Mechanismus:** Webhook-basiert (GitLab `Push Events`, `Issue Events`, `Pipeline Events`, `Merge Request Events`) — schreibt `direction='inbound'` in `sync_outbox` (selber Pfad wie Sentry/YouTrack)
  - **Webhook-Setup:** `POST /webhooks/ingest/<token>` empfängt GitLab-Events; Token via `POST /api/webhooks { "source": "gitlab" }` generiert
  - **Event-Mapping:**

    | GitLab Event | Hivemind-Ziel |
    | --- | --- |
    | `issue.opened` / `issue.reopened` | Triage `[UNROUTED]` |
    | `merge_request.merged` | Task-Artefakt-Link (optional: Epic-Verknüpfung) |
    | `pipeline.failed` | Triage `[UNROUTED]` (als Bug-Kandidat) |
    | `push` | Kartograph-Trigger (Code-Änderung → Follow-up-Session) |

  - **MCP-Tool-Wrapper:** `hivemind-get_gitlab_mr`, `hivemind-get_gitlab_pipeline` — Read-only, für Architekt/Worker-Kontext
- [ ] **GitHub Webhook Consumer**: GitHub als Datenquelle (Issues, PRs, Actions, Projects V2) — parallel zum GitLab-Consumer
  - **Auth:** HMAC-SHA256 Signatur-Validierung (`X-Hub-Signature-256` Header) + PAT via `HIVEMIND_GITHUB_TOKEN` oder GitHub App Installation Token
  - **Ingest-Mechanismus:** Webhook-basiert — schreibt `direction='inbound'` in `sync_outbox` (selber Pfad wie GitLab/Sentry/YouTrack)
  - **Webhook-Endpoint:** `POST /api/webhooks/github` (dediziert) oder generisch über `/api/webhooks/ingest/<token>`
  - **Event-Mapping:**

    | GitHub Event | Hivemind-Ziel |
    | --- | --- |
    | `issues.opened` / `issues.reopened` | Triage `[UNROUTED]` |
    | `pull_request.opened` | Task-Artefakt-Link |
    | `pull_request.merged` | Task-Completion-Trigger |
    | `check_run.completed` (failure) | Triage `[UNROUTED]` (Bug-Kandidat) |
    | `push` | Kartograph-Trigger (Code-Änderung → Follow-up-Session) |
    | `workflow_run.completed` | CI-Status-Sync |
    | `projects_v2_item.edited` | GitHub Projects Sync (→ s.u.) |
    | `release.published` | Informational (Wiki/Notification) |

  - **MCP-Tool-Wrapper:** `hivemind-get_github_pr`, `hivemind-get_github_issue`, `hivemind-get_github_check_status` — Read-only, für Architekt/Worker-Kontext
  - **Env-Vars:** `HIVEMIND_GITHUB_WEBHOOK_SECRET` (HMAC), `HIVEMIND_GITHUB_TOKEN` (PAT), `HIVEMIND_GITHUB_URL` (Default: `https://api.github.com`, für GitHub Enterprise: custom)
- [ ] **GitHub Models Provider**: GitHub Models API als AI-Provider — Zugang zu GPT-4o, Claude, Llama, Mistral etc. über einen einzigen GitHub PAT
  - Neuer Provider-Typ `github_models` in `ai_provider_configs`
  - OpenAI-kompatibles SDK (`openai` Python-Package) mit `base_url="https://models.inference.ai.azure.com"`
  - Auth: GitHub PAT (`HIVEMIND_GITHUB_TOKEN`) — kein separater AI-API-Key nötig
  - **Model-Katalog:** Automatisches Laden verfügbarer Modelle via `GET https://models.inference.ai.azure.com/models`
  - **Rate-Limits:** Free Tier: 15 RPM / 150k TPD — Low Tier: 20 RPM — beachten bei Conductor-Parallelisierung
  - **Tool-Calling:** GitHub Models API unterstützt Tool-Calling (tool names: `_` statt `/` Konvention)
  - **Vorteil:** Ein PAT → mehrere Modelle verschiedener Anbieter (Azure-gehostet) — kein Multi-Key-Management
- [ ] **GitHub Actions Agent**: Hivemind-Agents und Guards in GitHub Actions Pipelines ausführen
  - **3 Betriebsmodi:**
    1. **AI-Provider-Modus:** GitHub Actions Workflow ruft GitHub Models API als AI-Provider (günstig, GITHUB_TOKEN nativ verfügbar)
    2. **Guard-Modus:** CI-Guards (Lint, Test, Security) laufen als GitHub Actions Steps → Ergebnis wird via `hivemind-report_guard_result` zurückgemeldet
    3. **Agent-in-CI-Modus:** Kompletter Hivemind-Agent läuft im CI-Runner (für Code-Generierung + sofortigen Commit)
  - **Conductor-Integration:** Neues Feld `execution_mode` in `conductor_dispatches`: `local` (Default, Backend-intern) oder `github_actions` (→ Workflow Dispatch)
  - **GitHub Actions Workflow Dispatch:** Conductor triggert via `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches` mit Task-Key als Input
  - **Ergebnis-Rückmeldung:** Agent im CI ruft `POST /api/mcp/call` mit `hivemind-submit_result` am Ende des Workflow
  - **Commit Status Checks:** Guard-Ergebnisse werden als GitHub Commit Status (`POST /repos/{owner}/{repo}/statuses/{sha}`) zurückgeschrieben
  - **Security:** `HIVEMIND_API_TOKEN` als GitHub Actions Secret; Workflow hat `contents: write` + `statuses: write` Permissions
- [ ] **GitHub Projects V2 Sync**: Bidirektionale Synchronisation Hivemind ↔ GitHub Projects V2
  - **Sync-Richtung Hivemind→GitHub:** Via `sync_outbox` (`direction='outbound'`, `system='github'`) — Task-State-Changes aktualisieren GitHub Board
  - **Sync-Richtung GitHub→Hivemind:** Via Webhooks (`projects_v2_item.*` Events) — Board-Änderungen als `[UNROUTED]` ingestiert
  - **State-Mapping:** `incoming→Backlog`, `scoped/ready→Todo`, `in_progress→In Progress`, `in_review→In Review`, `done→Done`
  - **WICHTIG:** GitHub Board-Änderungen erzeugen NIE automatische State-Changes in Hivemind (Review-Gate-Schutz) — Triage entscheidet
  - **API:** GitHub Projects V2 = ausschließlich GraphQL (`POST /graphql`) — kein REST
  - **Konfiguration:** Per Project in `project_integrations`-Tabelle (Repo, Project-ID, Field-Mapping)
  - **Rate-Limit:** GitHub GraphQL: 5000 Points/h — Batch-Operationen beachten
- [ ] **MCP Bridge / Gateway (Meta-MCP)**: Hivemind als zentraler MCP-Proxy für externe MCP-Server
  - **Konzept:** Hivemind ist MCP-Server (für Agents) UND MCP-Client (zu GitHub MCP, GitLab MCP, Slack MCP, etc.)
  - **Namespace-Isolation:** Tools unter `hivemind-*` (lokal), `github/*` (proxied), `gitlab/*` (proxied), etc.
  - **Proxy-Layer:** Jeder Tool-Call durchläuft RBAC → Audit → Rate-Limiting → Forward an externen MCP-Server
  - **Transport:** stdio, SSE, HTTP — konfigurierbar pro Bridge
  - **Datenmodell:** `mcp_bridge_configs`-Tabelle (Name, Namespace, Transport, Command/URL, Env-Vars encrypted, Tool Allow/Blocklist)
  - **Tool-Discovery:** Beim Connect werden verfügbare Tools vom externen MCP-Server geladen und unter Namespace registriert
  - **Agent-Workflow:** Worker kann `github/create_branch`, `github/push_files`, `github/create_pull_request` nutzen — transparent über den Hivemind MCP-Server
  - **Security:**
    - Agents sehen NIE Credentials — alle externen API-Calls laufen durch den Backend-Proxy
    - Tool-Blocklist für gefährliche Operationen (z.B. `delete_repository` IMMER blockiert)
    - Env-Vars AES-256-GCM encrypted (selbes Pattern wie `ai_provider_configs`)
    - Namespace `hivemind` ist reserviert — kann nicht als Bridge-Namespace verwendet werden
  - **Graceful Degradation:** Wenn eine Bridge ausfällt, funktionieren lokale Tools + andere Bridges weiterhin
  - **Admin-API:** `GET/POST /api/admin/mcp-bridges`, `POST .../test`, `GET .../tools`
- [ ] Bibliothekar-Erweiterung für Auto-Modus: Per-Agent-Rolle Provider-Routing + provider-spezifische Token-Kalibrierung + adaptives Budget (pgvector-Similarity läuft bereits seit Phase 3; Phase 8 ergänzt Provider-Integration → [Agent-Provider-Routing](../agents/bibliothekar.md#agent-provider-routing))
- [ ] Nexus Grid 3D Backend: Graphdaten-Aggregation optimiert für große Codebases
- [ ] Auto-Escalation (Erweiterung): Phase 6 hat bereits SLA-basierte Escalation via Cron-Job (Decision-SLA > 72h → `escalated`). Phase 8 ergänzt **AI-gestützte proaktive Escalation** — der AI-Provider analysiert blockierte Tasks und entscheidet autonom über Eskalations-Zeitpunkt und Backup-Owner-Auswahl, ohne auf den Cron-Zyklus zu warten.
- [ ] **Conductor-Orchestrator** (→ [autonomy-loop.md](../features/autonomy-loop.md)):
  - Event-driven Backend-Service, reagiert auf State-Transitions und dispatcht Agenten
  - 12 Dispatch-Regeln (Task-State-, Epic-State-, Event-Trigger → Agent + Prompt-Typ)
  - Cooldown- und Idempotenz-Mechanismus (kein doppeltes Dispatching)
  - `conductor_dispatches` Tabelle für Audit-Trail
  - Env-Vars: `HIVEMIND_CONDUCTOR_ENABLED` (bool), `HIVEMIND_CONDUCTOR_PARALLEL` (int), `HIVEMIND_CONDUCTOR_COOLDOWN_SECONDS` (int)
  - Deaktivierbar pro Projekt (Fallback: manuelle Prompt Station)
- [ ] **Reviewer-Agent**: 7. AI-Agent-Rolle für automatisiertes Code-Review (→ [Reviewer-Skill](../features/agent-skills.md#-reviewer-skill-phase-8))
  - Prüft Task-Ergebnisse gegen DoD, Guard-Ergebnisse, Skill-Instruktionen
  - MCP-Tool: `submit_review_recommendation` (→ [mcp-toolset.md](../architecture/mcp-toolset.md#reviewer-writes-phase-8))
  - Confidence-basiert: `approve` / `reject` / `needs_human_review`
  - Dispatch nur wenn `governance.review ≠ 'manual'`
- [ ] **Governance-Levels**: Konfigurierbare Autonomie-Stufen pro Entscheidungstyp (→ [autonomy-loop.md](../features/autonomy-loop.md#3-governance-levels))
  - 3 Stufen: `manual` (Mensch entscheidet), `assisted` (AI empfiehlt, Mensch bestätigt), `auto` (AI entscheidet mit Grace Period)
  - 7 Entscheidungstypen: `review`, `epic_proposal`, `epic_scoping`, `skill_merge`, `guard_merge`, `decision_request`, `escalation`
  - Gespeichert in `app_settings.governance` (JSON)
  - Auto-Bedingungen + Safeguards pro Typ (z.B. Review: nie auto-reject, immer Grace Period)
  - `review_recommendations` Tabelle für AI-Review-Audit-Trail
  - Ist-Stand: Der explizite `assisted`/`auto` Split ist derzeit produktiv nur fuer `review` umgesetzt; die anderen Governance-Typen nutzen aktuell denselben AI-Dispatch-Gate und unterscheiden sich erst wieder, wenn der jeweilige Domain-Flow erweitert wird
- [ ] **Worker-Endpoint-Pool** (optional): Mehrere Self-Hosted-Endpoints für eine Agent-Rolle (→ [data-model.md — ai_provider_configs](../architecture/data-model.md))
  - `endpoints` JSONB-Array in `ai_provider_configs` statt Single-`endpoint`: `[{"url": "http://gpu1:11434", "weight": 1}, ...]`
  - Pool-Strategien: `round_robin` (Default), `weighted` (nach GPU-Stärke), `least_busy` (wenigste aktive Dispatches)
  - Conductor dispatcht parallele Worker-Tasks an verschiedene Endpoints — ein Subtask pro Endpoint gleichzeitig möglich
  - RPM-Limit gilt **pro Endpoint** im Pool (nicht aggregiert) — ermöglicht höheren Gesamt-Throughput
  - Health-Check: Conductor prüft Endpoint-Verfügbarkeit per Ping vor Dispatch; unhealthy Endpoints werden temporär übersprungen (60s Cooldown)
  - **Subtask-Aggregation:** Wenn alle Subtasks eines Parent-Tasks `done` sind, erzeugt der Conductor automatisch einen Merge-Prompt für den Parent-Task. Kein neuer Agent — der Architekt-Prompt-Typ `merge_subtasks` assembliert die Ergebnisse. Der Parent-Task geht danach auf `in_review`.
  - **Kein Pflicht-Feature:** Funktioniert nur mit `ollama`/`custom`-Providern (Self-Hosted). Cloud-Provider haben eigenes Load-Balancing.
  - **Monitoring:** Prompt Station zeigt Pool-Status pro Endpoint (healthy/unhealthy, aktive Dispatches, avg Response Time)

### Frontend
- [ ] AI-Provider-Config in Settings:
  - Per-Agent-Rolle: Provider-Auswahl (inkl. `github_models`), Modell, Endpoint (Single oder Pool), API-Key, Token-Budget, RPM-Limit
  - GitHub Models: Modell-Katalog-Browser — verfügbare Modelle werden vom API geladen
  - Endpoint-Pool-Editor: Endpoints hinzufügen/entfernen, Weight pro Endpoint, Pool-Strategie wählen
  - Global-Fallback: Ein Default-Provider für nicht einzeln konfigurierte Rollen
  - Hybrid-Modus: Einzelne Rollen manuell (BYOAI), andere automatisiert
  - Test-Button pro Rolle (Ping + Token-Count-Validierung)
  - Schrittweise Migration: Erst eine Rolle automatisieren, dann weitere hinzufügen
- [ ] **MCP Bridge Config** in Settings (Admin-only):
  - Bridge-Liste: Name, Namespace, Transport, Status (connected/disconnected/error)
  - Bridge hinzufügen/bearbeiten: Transport wählen (stdio/SSE), Command/URL, Env-Vars (sicher)
  - Tool-Katalog: Verfügbare Tools pro Bridge anzeigen, Allow/Blocklist konfigurieren
  - Test-Button pro Bridge (Connect + Tool-Discovery)
  - Health-Status: Active connections, error rate, last call timestamp
- [ ] Prompt Station: Auto-Modus
  - Kein Prompt-Card mehr sichtbar
  - Stattdessen: Monitoring-Ansicht (aktive Agenten, Token-Verbrauch, Status)
  - "Manuell eingreifen"-Button jederzeit verfügbar
- [ ] Nexus Grid 3D (WebGL / Three.js):
  - Toggle-Button: [2D] ↔ [3D]
  - Fly-Through-Navigation (Orbit-Controls via Three.js)
  - Fog of War in 3D erhalten (unerkundete Nodes als transparente Sphären)
  - **Performance-Ziel:** 1000 Nodes @ 30 FPS auf Mid-Range-GPU (GTX 1060 / RX 580 Äquivalent)
  - **Implementierungsstrategie:**
    - Instanced Rendering (`THREE.InstancedMesh`) für alle Nodes gleichen Typs — ein Draw-Call pro Node-Typ statt 1000 einzelne
    - Frustum Culling: Three.js default (automatisch für Meshes)
    - Level-of-Detail (LOD): Nodes außerhalb des Sichtbereichs → einfachere Geometrie (8-Polygon-Sphäre statt 32)
    - Kanten als `THREE.LineSegments` mit Buffer Geometry (kein individuelles `Line`-Objekt pro Edge)
    - Vue-Reaktivität bleibt **außerhalb** des Three.js-Render-Loops — keine reaktiven Refs im Animation-Frame
    - Fog-of-War-Overlay: Shader-Material (GLSL) auf einer flachen Plane über der Szene — kein DOM-Element
- [ ] KPI-Dashboard (vollständig): alle 6 KPIs mit historischen Graphen (7/30-Tage-Zeitreihe)
- [ ] **Governance-Tab** in Settings (→ [autonomy-loop.md](../features/autonomy-loop.md#3-governance-levels)):
  - Pro Entscheidungstyp: Dropdown `manual | assisted | auto`
  - Auto-Konfiguration: Confidence-Threshold, Grace-Period-Minuten
  - Safeguard-Anzeige (welche Einschränkungen gelten pro Typ)
  - Autonomie-Spektrum-Visualisierung (aktueller Stand)
- [ ] **AI-Review-Panel** in Task-Detail:
  - Bei `governance.review = 'assisted'`: Review-Empfehlung mit Checklist, Confidence-Badge, 1-Click Approve/Reject
  - Bei `governance.review = 'auto'`: Grace-Period-Countdown + "Eingreifen"-Button
  - Immer: Link zum vollständigen Review-Recommendation-Audit-Trail

---

## Auto-Modus Ablauf

```
Phase 1-7 (Manuell):
  Prompt Station → User kopiert → AI-Client → MCP

Phase 8 (Auto-Modus — per Agent-Rolle konfigurierbar):
  Event/State-Transition → Conductor dispatcht Agent
    → Lookup ai_provider_configs[agent_role]
    → Konfiguriert: sendet an Provider (Claude/OpenAI/Gemini/Ollama/GitHub Models)
    → execution_mode: 'local' (Backend) oder 'github_actions' (CI-Runner)
    → Nicht konfiguriert: Fallback auf app_settings.ai_provider
    → Kein Provider: BYOAI-Modus (Prompt Station zeigt Prompt)
  AI-Provider → ruft MCP-Tools auf (lokal hivemind-* + proxied github/*, gitlab/*)
    → MCP Gateway proxied externe Tools transparent (RBAC + Audit)
  State-Transition → Conductor dispatcht nächsten Agent
    → z.B. Task done → Gaertner, Task in_review → Reviewer
  Governance-Level entscheidet bei Gate-Points:
    manual:   Owner entscheidet (wie bisher)
    assisted: AI empfiehlt, Owner bestätigt (1-Click)
    auto:     AI entscheidet, Grace Period für Veto
  User → sieht Monitoring, greift nur bei Bedarf ein
```

> Praktisch gilt aktuell: `review=auto` fuehrt nach Reviewer-Empfehlung zu Grace-Period + Auto-Approve. Die anderen Typen (`epic_proposal`, `epic_scoping`, `skill_merge`, `decision_request`, `escalation`) aktivieren derzeit denselben Agentenpfad wie `assisted`.

**Kein Architekturbruch:** Gleicher Prompt, gleiche MCP-Calls, gleiche Validierung. Nur der manuelle Copy-Paste-Schritt entfällt — und jede Rolle kann ihren optimalen Provider nutzen. Der MCP Gateway erweitert das Tool-Ökosystem transparent um externe MCP-Server (GitHub, GitLab, etc.) — Agents merken keinen Unterschied zwischen lokalen und proxied Tools.

### Token-Counting im Auto-Modus

In Phase 1–7 verwendet Hivemind `tiktoken cl100k_base` als universelle Approximation (kompatibel mit GPT-4, Claude, den meisten LLMs). Im Auto-Modus ist der Provider per Rolle bekannt — Phase 8 kann auf provider-spezifische Tokenizer wechseln:

| Provider | Tokenizer | Genauigkeit |
| --- | --- | --- |
| `anthropic` (Claude) | `tiktoken cl100k_base` (Approximation, < 2% Abweichung) | Ausreichend für Budget-Planung |
| `openai` (GPT-4/4o) | `tiktoken cl100k_base` (exakt) | Exakt |
| `google` (Gemini) | `tiktoken cl100k_base` (Approximation) | Ausreichend |
| `ollama` (lokal) | `tiktoken cl100k_base` (Approximation) | Ausreichend |
| `github_models` (Azure-hosted) | `tiktoken cl100k_base` (Approximation, Modell-abhängig) | Ausreichend |

**Phase-8-Verhalten:** Das Backend wählt den Tokenizer automatisch basierend auf `ai_provider_configs[agent_role].provider`. Für Anthropic wird `cl100k_base` beibehalten (Anthropic veröffentlicht keinen offiziellen öffentlichen Tokenizer; `cl100k_base` ist de-facto Standard). Eine Provider-spezifische Token-Count-Kalibrierung (Offset-Faktor pro Provider) kann via `HIVEMIND_TOKEN_COUNT_CALIBRATION` Env-Var eingestellt werden (JSON: `{"anthropic": 1.05, "openai": 1.0, "google": 1.1, "ollama": 1.0, "github_models": 1.0}`).

> **Kein Breaking Change:** `tiktoken cl100k_base` bleibt der Default — Phase 8 ergänzt nur die Kalibrierungsoption. Token Radar und Budget-Warnungen funktionieren unverändert.

---

## Acceptance Criteria

### Definition of Ready (alle müssen erfüllt sein vor Phase 8 Start)
- [ ] RBAC und Audit für alle Writes produktiv (Phase 2 ✓)
- [ ] Idempotenz und Optimistic Locking für alle mutierenden Domain-Writes (Phase 2 ✓)
- [ ] Review-Gate verhindert direkte `done`-Transitions (Phase 2 ✓)
- [ ] Eskalations-SLA mit Backup-Owner und Admin-Fallback (Phase 6 ✓)
- [ ] KPI-Baselines über 2 Wochen stabil (Phase 7 Messung ✓)

### Phase 8 Specific
- [ ] API-Keys werden sicher gespeichert (nicht im Plaintext in DB)
  - **Speicherort:** `ai_provider_configs` mit `api_key_encrypted` + `api_key_nonce` pro Agent-Rolle; `app_settings.ai_api_key_encrypted` als Global-Fallback
  - **Verschlüsselung:** AES-256-GCM mit Schlüssel abgeleitet aus `HIVEMIND_KEY_PASSPHRASE` (identisch zur Ed25519-Key-Verschlüsselung) via HKDF-SHA256 (separater Salt für API-Key-Kontext)
  - **Ablauf:** Frontend sendet Plaintext-Key via HTTPS → Backend verschlüsselt sofort (AES-256-GCM) → speichert Ciphertext + Nonce → Plaintext nie persistiert
  - **Entschlüsselung:** Nur im Speicher beim aktiven API-Call; Schlüssel wird nach Verwendung aus dem Speicher gelöscht
  - **Alternative:** Wenn `HIVEMIND_AI_API_KEY` als Env-Var gesetzt ist, wird dieses als Global-Fallback bevorzugt (kein DB-Eintrag nötig — für Deployments die Secrets über Env-Vars managen). Per-Role-Keys haben Vorrang.
- [ ] AI-Provider sendet Prompt und empfängt MCP-Calls korrekt
- [ ] Review-Gate auch im Auto-Modus aktiv (kein direktes `done`)
- [ ] "Manuell eingreifen"-Button schaltet zurück auf manuelle Prompt Station
- [ ] Nexus Grid 3D lädt und navigierbar für Codebases > 1000 Nodes
- [ ] GitLab Issues werden als neue Epics/Tasks ingestiert
- [ ] GitHub Issues/PRs werden via Webhooks korrekt ingestiert (HMAC-SHA256 validiert)
- [ ] GitHub Models Provider funktioniert als AI-Provider (Tool-Calling + Streaming)
- [ ] GitHub Actions Workflow Dispatch triggert korrekt auf Conductor-Befehl
- [ ] GitHub Actions Guard-Ergebnisse werden via `report_guard_result` zurückgemeldet
- [ ] GitHub Projects V2 Sync: Task-State-Changes reflektieren sich im GitHub Board
- [ ] GitHub Projects V2 Sync: Board-Änderungen landen als `[UNROUTED]` in Triage (kein auto State-Change)
- [ ] MCP Bridge: Externe MCP-Server können verbunden und Tools genutzt werden
- [ ] MCP Bridge: Tool-Blocklist verhindert gefährliche Operationen (`delete_repository`)
- [ ] MCP Bridge: Audit-Log erfasst alle proxied Tool-Calls (inkl. Arguments + Result)
- [ ] MCP Bridge: Agents erhalten NIE Credentials — nur Backend-Proxy hat Zugriff
- [ ] Conductor dispatcht Agenten korrekt auf State-Transitions (12 Trigger getestet)
- [ ] Conductor Cooldown verhindert doppeltes Dispatching (Idempotenz-Test)
- [ ] Reviewer-Agent gibt korrekte Empfehlungen mit Confidence-Score ab
- [ ] `submit_review_recommendation` ändert nie direkt den Task-State
- [ ] Governance-Levels konfigurierbar via Settings UI (alle 7 Typen × 3 Stufen)
- [ ] Auto-Review: Grace Period läuft ab → auto-approve bei Confidence ≥ Threshold
- [ ] Auto-Review: Grace Period kann via "Eingreifen"-Button unterbrochen werden
- [ ] Auto-Reject ist NICHT möglich — `reject` Empfehlung erfordert immer menschliche Bestätigung

---

## Abhängigkeiten

- Alle Phasen 1–7 abgeschlossen und KPI-stabil

---

## Post-Phase-8: Evaluierungspunkte

- Redis für Outbox wenn Volumen > 10k Events/Tag
- Multi-Instanz-Setup (mehrere Teams auf einer Plattform)
- Nexus Grid: Diff-Ansicht (welche Nodes haben sich seit letztem Kartograph-Run verändert)
- Skill-Empfehlungs-System: AI schlägt proaktiv Skills vor ohne Gaertner-Run
- Worker-Pool Auto-Scaling: Endpoints dynamisch hinzufügen/entfernen basierend auf Queue-Tiefe
- GitHub Copilot CLI Integration: `gh copilot suggest` / `gh copilot explain` als ergänzende Agent-Werkzeuge
- GitHub App statt PAT: Finer-grained Permissions, Installation Tokens, höhere Rate-Limits
- MCP Bridge: Weitere Server anbinden (Slack MCP, Jira MCP, Notion MCP, etc.)
- MCP Bridge: Tool-Composability — ein Master-Tool das mehrere Bridge-Tools orchestriert
- GitHub Actions: Self-Hosted Runner für höhere Parallelisierung und GPU-Zugriff
