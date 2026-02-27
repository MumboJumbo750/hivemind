# Phase 8 — Volle Autonomie

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** AI-Client konsumiert Prompts direkt via API-Key. GitLab MCP Consumer. 3D Nexus Grid. Kein Architekturbruch.

**AI-Integration:** API-Keys für Claude/OpenAI. Hivemind schickt Prompts direkt an AI-API. MCP-Calls laufen weiterhin identisch.

**Voraussetzung:** Alle Kriterien aus [Definition of Ready](./overview.md#definition-of-ready-für-phase-8-autonomous-mode) erfüllt.

---

## Deliverables

### Backend
- [ ] AI-Provider-Service: sendet generierte Prompts direkt an Claude/OpenAI API
  - Provider-Abstraktion: `anthropic`, `openai`, `ollama` (lokal)
  - Gleicher Prompt wie bisher — kein Unterschied für MCP-Tools
  - Rate-Limiting + Retry bei API-Fehlern
- [ ] GitLab MCP Consumer: GitLab als Datenquelle (MRs, Pipelines, Issues)
- [ ] Bibliothekar als echter Backend-Service (pgvector-Similarity, kein Prompt mehr)
- [ ] Nexus Grid 3D Backend: Graphdaten-Aggregation optimiert für große Codebases
- [ ] Auto-Escalation: System eskaliert autonom nach SLA-Regeln ohne manuelle Trigger

### Frontend
- [ ] AI-Provider-Config in Settings:
  - Provider-Auswahl (Manuell / Claude / OpenAI)
  - API-Key-Eingabe (verschlüsselt gespeichert)
  - Modell-Auswahl
  - Test-Button
- [ ] Prompt Station: Auto-Modus
  - Kein Prompt-Card mehr sichtbar
  - Stattdessen: Monitoring-Ansicht (aktive Agenten, Token-Verbrauch, Status)
  - "Manuell eingreifen"-Button jederzeit verfügbar
- [ ] Nexus Grid 3D (WebGL / Three.js):
  - Toggle-Button: [2D] ↔ [3D]
  - Fly-Through-Navigation
  - Fog of War in 3D erhalten
- [ ] KPI-Dashboard (vollständig): alle 6 KPIs mit historischen Graphen

---

## Auto-Modus Ablauf

```
Phase 1-7 (Manuell):
  Prompt Station → User kopiert → AI-Client → MCP

Phase 8 (Auto-Modus):
  Hivemind → generiert Prompt → sendet an Claude API
  Claude API → ruft MCP-Tools auf → schreibt Ergebnis
  Hivemind → Review-Gate weiterhin aktiv (Owner reviewed)
  User → sieht Monitoring, greift nur bei Bedarf ein
```

**Kein Architekturbruch:** Gleicher Prompt, gleiche MCP-Calls, gleiche Validierung. Nur der manuelle Copy-Paste-Schritt entfällt.

### Token-Counting im Auto-Modus

In Phase 1–7 verwendet Hivemind `tiktoken cl100k_base` als universelle Approximation (kompatibel mit GPT-4, Claude, den meisten LLMs). Im Auto-Modus ist der Provider bekannt — Phase 8 kann auf provider-spezifische Tokenizer wechseln:

| Provider | Tokenizer | Genauigkeit |
| --- | --- | --- |
| `anthropic` (Claude) | `tiktoken cl100k_base` (Approximation, < 2% Abweichung) | Ausreichend für Budget-Planung |
| `openai` (GPT-4/4o) | `tiktoken cl100k_base` (exakt) | Exakt |
| `ollama` (lokal) | `tiktoken cl100k_base` (Approximation) | Ausreichend |

**Phase-8-Verhalten:** Das Backend wählt den Tokenizer automatisch basierend auf `app_settings.ai_provider`. Für Anthropic wird `cl100k_base` beibehalten (Anthropic veröffentlicht keinen offiziellen öffentlichen Tokenizer; `cl100k_base` ist de-facto Standard). Eine Provider-spezifische Token-Count-Kalibrierung (Offset-Faktor pro Provider) kann via `HIVEMIND_TOKEN_COUNT_CALIBRATION` Env-Var eingestellt werden (JSON: `{"claude": 1.05, "gpt4": 1.0}`).

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
- [ ] API-Key wird sicher gespeichert (nicht im Plaintext in DB)
- [ ] AI-Provider sendet Prompt und empfängt MCP-Calls korrekt
- [ ] Review-Gate auch im Auto-Modus aktiv (kein direktes `done`)
- [ ] "Manuell eingreifen"-Button schaltet zurück auf manuelle Prompt Station
- [ ] Nexus Grid 3D lädt und navigierbar für Codebases > 1000 Nodes
- [ ] GitLab Issues werden als neue Epics/Tasks ingestiert

---

## Abhängigkeiten

- Alle Phasen 1–7 abgeschlossen und KPI-stabil

---

## Post-Phase-8: Evaluierungspunkte

- Redis für Outbox wenn Volumen > 10k Events/Tag
- Multi-Instanz-Setup (mehrere Teams auf einer Plattform)
- Nexus Grid: Diff-Ansicht (welche Nodes haben sich seit letztem Kartograph-Run verändert)
- Skill-Empfehlungs-System: AI schlägt proaktiv Skills vor ohne Gaertner-Run
