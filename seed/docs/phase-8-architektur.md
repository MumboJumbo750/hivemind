---
epic_ref: "EPIC-PHASE-8"
title: "Phase 8 — Architektur-Kontext"
---

# Phase 8 — Volle Autonomie

## Überblick

Phase 8 ist der Übergang zur vollständigen AI-Autonomie: AI-Provider konsumieren Prompts direkt, der Conductor orchestriert Agenten, der Reviewer prüft automatisiert, und Governance-Levels steuern den Autonomiegrad. Dazu kommen MCP Bridge/Gateway (Meta-MCP), GitHub/GitLab-Integration und 3D Nexus Grid.

## Architektur-Entscheidungen

### Per-Agent-Rolle AI-Provider-Routing
Jede Agentenrolle (Kartograph, Stratege, Architekt, Worker, Gaertner, Triage) kann einen eigenen Provider + Modell + Endpoint nutzen. Fallback-Kaskade: Rollen-Config → Global-Default → BYOAI-Modus.

### Conductor-Orchestrator
Event-driven Backend-Service: reagiert auf State-Transitions und dispatcht den passenden Agenten. 12 Dispatch-Regeln, Cooldown + Idempotenz. Deaktivierbar pro Projekt.

### Reviewer-Agent (7. Agent-Rolle)
Automatisiertes Code-Review gegen DoD, Guard-Ergebnisse und Skill-Instruktionen. Confidence-basiert: `approve` / `reject` / `needs_human_review`. Dispatch nur bei `governance.review ≠ 'manual'`.

### Governance-Levels
3 Stufen pro Entscheidungstyp: `manual` (Mensch entscheidet), `assisted` (AI empfiehlt, Mensch bestätigt), `auto` (AI entscheidet mit Grace Period). 7 konfigurierbare Entscheidungstypen.

### MCP Bridge / Gateway (Meta-MCP)
Hivemind als MCP-Server UND MCP-Client. Namespace-Isolation: `hivemind-*` (lokal), `github/*` (proxied), `gitlab/*` (proxied). Zentrale RBAC-, Audit- und Rate-Limiting-Schicht für alle Tool-Quellen.

### GitHub Models Provider
GitHub PAT → Zugang zu GPT-4o, Claude, Llama via Azure-Infrastruktur. Ein Token, viele Modelle.

### GitHub Actions Agent
3 Modi: AI-Provider-Modus (CI nutzt GitHub Models API), Guard-Modus (CI-Guards → `report_guard_result`), Agent-in-CI (kompletter Hivemind-Agent im CI-Runner). Conductor dispatcht via Workflow Dispatch.

## Auto-Modus-Ablauf

```
Phase 1-7 (Manuell):
  Prompt Station → User kopiert → AI-Client → MCP

Phase 8 (Auto):
  State-Transition → Conductor dispatcht Agent
    → ai_provider_configs[rolle] → Provider-Client
    → execution_mode: local | github_actions
    → Kein Provider: BYOAI-Fallback
  AI-Provider → MCP-Tools (lokal + proxied)
  State-Transition → nächster Agent
  Governance-Level → Gate-Point-Entscheidung
```

## Relevante Skills
- `ai-provider-service` — AI-Provider-Integration
- `conductor-orchestrator` — Conductor-Logik
- `review-recommendation` — Review-Agent-Pattern
- `governance-level` — Governance-Konfiguration
- `mcp-bridge-gateway` — MCP Bridge/Gateway
- `github-models-provider` — GitHub Models API
- `github-actions-agent` — GitHub Actions Integration
- `github-webhook-consumer` — GitHub Webhook-Verarbeitung
- `nexus-grid-3d` — 3D-Visualisierung
- `auto-mode-monitoring` — Auto-Modus-Monitoring
