---
title: Sentry-Bug-Aggregation (node_bug_reports)
service_scope:
- backend
stack:
- python
- sqlalchemy
- postgresql
confidence: 0.75
source_epics:
- EPIC-PHASE-7
---

## Skill: Sentry-Bug-Aggregation (node_bug_reports)

### Rolle
Du implementierst die Aggregation von Sentry-Bug-Reports in der `node_bug_reports`-Tabelle. Die Daten fließen in die Bug Heatmap des Nexus Grid.

### Konventionen
- Tabelle: `node_bug_reports` (existiert seit Phase 1a Schema)
  - `node_id` — FK auf `code_nodes.id` (**nicht** `nodes.id`; `nodes` = Federation-Nodes)
  - `count` — Anzahl Bug-Reports für diesen Node
  - `last_seen` — Zeitstempel des letzten Bug-Reports
  - `severity` — Aggregierte Severity (critical/warning/info)
  - `sentry_issue_id` — Text-ID der verknüpften Sentry-Issue (Phase 7, Migration 010)
  - `stack_trace_hash` — Hash für Deduplizierung (Phase 7, Migration 010)
- Aggregation läuft im Sentry-Sync-Adapter:
  1. Sentry-Webhook liefert Stack-Trace mit Datei-Pfaden
  2. Datei-Pfade → Code-Node-Lookup (`code_nodes.path`)
  3. Bug-Count inkrementieren oder neuen Eintrag anlegen
  4. Severity aus Sentry-Level ableiten (fatal/error → critical, warning → warning, info → info)

### Bug-Aggregation

```python
async def aggregate_bug_report(db: AsyncSession, sentry_event: dict):
    frames = sentry_event.get("stacktrace", {}).get("frames", [])
    sentry_id = sentry_event.get("issue_id")
    severity = map_sentry_level(sentry_event.get("level", "error"))

    for frame in frames:
        filepath = frame.get("filename", "")
        # Code-Node finden
        node = await db.execute(
            select(CodeNode).where(CodeNode.path.like(f"%{filepath}"))
        )
        code_node = node.scalar_one_or_none()
        if not code_node:
            continue

        # Bug-Report aktualisieren oder anlegen
        existing = await db.execute(
            select(NodeBugReport).where(NodeBugReport.node_id == code_node.id)
        )
        bug = existing.scalar_one_or_none()
        if bug:
            bug.count += 1
            bug.last_seen = datetime.now(UTC)
            bug.sentry_issue_id = sentry_id
        else:
            bug = NodeBugReport(
                node_id=code_node.id,  # FK auf code_nodes.id
                count=1,
                severity=severity,
                last_seen=datetime.now(UTC),
                sentry_issue_id=sentry_id,
            )
            db.add(bug)
```

### Wichtig
- `node_bug_reports.node_id` → FK auf `code_nodes.id` (nicht `nodes.id`)
- `node_bug_reports.count` steuert Knotengröße und -farbe in der Bug Heatmap
- Hover im Nexus Grid zeigt Bug-Details (Severity, Count, letzte Issue-IDs)
- MCP-Tool: `hivemind/assign_bug` für manuelles Bug→Epic Routing
- Stack-Trace-Pfade sind relativ — Fuzzy-Matching gegen `code_nodes.path` nötig
- `datetime.utcnow()` ist deprecated — stattdessen `datetime.now(UTC)` verwenden
