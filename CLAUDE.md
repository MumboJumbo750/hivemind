# Hivemind — Claude Code Context

> Vollständiger Laufzeit-Kontext (Container, Befehle, MCP, Projektstruktur):
> **→ [AGENTS.md](AGENTS.md)**
>
> Dieses File enthält nur Claude-spezifische Ergänzungen.

---

## Kommunikation

- Sprache: **Deutsch**
- Keine Umsetzung ohne explizite Freigabe

## Workflow-Regeln

- Review-Gate ist **immer** Pflicht — kein direktes `done` via MCP
- MCP State-Chain: `scoped → in_progress → (submit_result) → in_review → (Review-Gate) → done`
- Vor jeder Implementierung: zugehörige Skills in `seed/skills/` lesen

## Persistente Memory

Memory-Datei (projektübergreifend): `~/.claude/projects/c--projects-hivemind-memory/MEMORY.md`

## Codebase-Konventionen (Kurzreferenz)

Vollständige Konventionen → [AGENTS.md](AGENTS.md)

- **Unified Key System:** Alle Keys via PG-Sequences in `backend/app/services/key_generator.py` — Format `{PREFIX}-{n}` (EPIC-, TASK-, SKILL-, WIKI-, GUARD-, DOC-)
- APScheduler-Jobs: `backend/app/services/scheduler.py` → `start_scheduler()` — **nie** `main.py`
- SyncOutbox: NUR `'pending'` und `'dead_letter'` — kein `'delivered'`, `'failed'`, `'dead'`
- Outbound-Erfolg: `db.delete(entry)` — kein Status-Update
- Inbound: `routing_state = 'routed'` setzen — Eintrag bleibt als Audit-Record
- `node_bug_reports.node_id` → FK auf `code_nodes.id` (nicht `nodes.id`)
