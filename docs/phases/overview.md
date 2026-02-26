# Phasen-Übersicht

← [Index](../../masterplan.md)

8 Phasen von "Datenfundament" bis "Volle Autonomie". UI-Entwicklung läuft **parallel** zu Backend-Phasen.

---

## Übersicht

| Phase | Backend | UI | AI-Integration |
| --- | --- | --- | --- |
| [Phase 1](./phase-1.md) | Datenfundament, State Machine, Audit | Prompt Station + Settings Skeleton | Keins — alles manuell |
| [Phase 2](./phase-2.md) | Identity & RBAC | Command Deck, Login, Notifications | Keins — alles manuell |
| [Phase F](./phase-f.md) | Federation Protocol, Peer Discovery, Epic-Sharing, Kartograph-Sync | Peer-Overview, Shared Map, Skill-Loadout | Keins — alles manuell |
| [Phase 3](./phase-3.md) | MCP Read-Tools + Bibliothekar-Prompt | Triage Station, Token Radar | Ollama Container (Embeddings) |
| [Phase 4](./phase-4.md) | Planer-Writes (Architekt) | Skill Lab, Audit-Log | — |
| [Phase 5](./phase-5.md) | Worker & Gaertner Writes | Wiki, Nexus Grid 2D | — |
| [Phase 6](./phase-6.md) | Triage & Eskalation | Decision Requests, SLA-UI | — |
| [Phase 7](./phase-7.md) | Externe Integration Hardening | Dead Letter, Bug Heatmap, Sync-Status | — |
| [Phase 8](./phase-8.md) | Volle Autonomie | 3D Nexus Grid, Auto-Modus | API-Keys, GitLab MCP Consumer |

> **Phase F ist strategischer Core** — Federation ist das Zielbild für kollaboratives Arbeiten. Operativ kann ein Team mit Shared Instance (Phase 2) starten und Federation später aktivieren; beide Betriebsarten bleiben kompatibel.

### Phase-F-Sequenzierung

```text
Lineare Pflichtsequenz:   Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 8

Phase F (optional):       Kann nach Phase 2 eingeschoben werden — vor, nach oder parallel zu Phase 3.
                          Voraussetzung: Phase 2 abgeschlossen (Identity & RBAC aktiv).
                          Keine Voraussetzung auf Phase 3+.

Empfohlene Reihenfolge für Teams:   Phase 1 → Phase 2 → Phase F → Phase 3 → ...
Solo-Entwickler (kein Peer):         Phase F überspringen oder nach Phase 5 nachholen.
```

**Kompatibilitätsgarantie:** Das Schema (inkl. `nodes`, `node_identity`, `origin_node_id`, `federation_scope`) wird bereits in Phase 1 angelegt. Phase F aktiviert darauf aufbauend das Federation-Protokoll — kein Migrations-Bruch.

---

## Definition of Ready für Phase 8 (Autonomous Mode)

Autonomous Mode wird erst aktiviert wenn alle Kriterien erfüllt sind:

1. RBAC und Audit für alle Writes produktiv (Phase 2)
2. Idempotenz und optimistic locking für alle mutierenden Domain-Writes aktiv (Phase 2)
3. Review-Gate verhindert direkte `done`-Transitions (Phase 2)
4. Eskalations-SLA mit Backup-Owner und Admin-Fallback verifiziert (Phase 6)
5. KPI-Baselines über mindestens 2 Wochen stabil gemessen (Phase 7)

---

## KPIs (ab Phase 3 messen)

| KPI | Zielwert |
| --- | --- |
| Routing-Precision bei Auto-Owner-Zuweisung | >= 85% |
| Median Zeit bis `scoped` nach Epic-Ingest | <= 4h |
| Anteil Tasks ohne Reopen nach `done` | >= 80% |
| Decision Requests innerhalb SLA gelöst | >= 95% |
| Skill-Proposals mit Entscheidung in 72h | >= 90% |
| Unauthorized Write Attempts | 0 toleriert |
