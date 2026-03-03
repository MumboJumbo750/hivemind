# Hivemind — GitHub Copilot Instructions

> Vollständiger Laufzeit-Kontext (Container, Befehle, MCP, Projektstruktur):
> **→ [AGENTS.md](../../AGENTS.md)**
>
> Dieses File enthält nur Copilot-spezifische Ergänzungen.

## Kommunikation

- Sprache: **Deutsch**
- Keine Umsetzung ohne explizite Freigabe

## Kritische Container-Regel

Backend-Befehle laufen **IMMER im Container** — der Host hat kein Python-Virtualenv.
Nutze `make`-Targets oder `podman compose exec backend ...` — nie direkt `pytest`, `alembic` etc. auf dem Host.

## Konventionen (Kurzreferenz)

- APScheduler-Jobs: `backend/app/services/scheduler.py` → `start_scheduler()` — **nie** `main.py`
- SyncOutbox: NUR `'pending'` und `'dead_letter'` — kein `'delivered'`, `'failed'`, `'dead'`
- `node_bug_reports.node_id` → FK auf `code_nodes.id` (nicht `nodes.id`)

## Referenz

Alle Details → [AGENTS.md](../../AGENTS.md)
