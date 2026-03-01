---
title: KPI-Aggregation & Dashboard-API
service_scope:
- backend
- frontend
stack:
- python
- fastapi
- sqlalchemy
- postgresql
- typescript
- vue3
confidence: 0.5
source_epics:
- EPIC-PHASE-7
---

## Skill: KPI-Aggregation & Dashboard-API

### Rolle
Du implementierst die Backend-Seite des KPI-Dashboards für Phase 7. Sechs Kern-KPIs werden aus bestehenden Tabellen aggregiert und über eine REST-API bereitgestellt.

### Konventionen
- Endpoint: `GET /api/kpis` — liefert alle 6 KPIs mit aktuellem Wert und Zielwert
- Cache: Stündlich gecacht (selbe Granularität wie SLA-Cron)
- Cache-Table: `kpi_snapshots` oder In-Memory-Cache via `app_settings`
- Update: APScheduler-Job (stündlich) berechnet KPI-Werte und cacht sie
- Phase 8 ergänzt: historische Graphen (Zeitreihe über 7/30 Tage)

### Die 6 Kern-KPIs

| KPI | Quelle | Berechnung | Ziel |
|-----|--------|-----------|------|
| Routing-Precision | `sync_outbox` (routed + routing_confidence) | Anteil korrekt gerouteter Events | >= 85% |
| Median Zeit bis scoped | `epics` (created_at → state='scoped' at) | Median Zeitdifferenz | <= 4h |
| Tasks ohne Reopen | `tasks` (state='done' ohne qa_failed History) | Anteil done ohne Reopen | >= 80% |
| Decision Requests in SLA | `decision_requests` (resolved_at - created_at) | Anteil innerhalb SLA | >= 95% |
| Skill-Proposals in 72h | `skills` (lifecycle pending_merge → merged/rejected) | Anteil mit Entscheidung in 72h | >= 90% |
| Unauthorized Writes | `mcp_invocations` (status=403) | Count | 0 |

### API-Response

```python
@router.get("/api/kpis")
async def get_kpis(db=Depends(get_db)):
    return {
        "kpis": [
            {
                "key": "routing_precision",
                "label": "Routing-Precision",
                "value": 0.87,
                "target": 0.85,
                "unit": "percent",
                "trend": "up",
                "updated_at": "2026-03-01T12:00:00Z",
            },
            # ... 5 weitere KPIs
        ],
        "cached_at": "2026-03-01T12:00:00Z",
    }
```

### KPI-Berechnung (Scheduled Job)

```python
async def compute_kpis(db: AsyncSession) -> list[dict]:
    kpis = []
    
    # 1. Routing Precision
    total_routed = await db.scalar(
        select(func.count()).where(SyncOutbox.routing_state == "routed")
    )
    correct_routed = await db.scalar(
        select(func.count()).where(
            SyncOutbox.routing_state == "routed",
            SyncOutbox.routing_confidence >= 0.85,
        )
    )
    precision = correct_routed / total_routed if total_routed > 0 else None
    kpis.append({"key": "routing_precision", "value": precision, "target": 0.85})
    
    # 2-6 analog aus tasks, decision_requests, skills, mcp_invocations
    return kpis
```

### Frontend-Darstellung
- Layout: 2x3 Grid mit KPI-Cards
- Jede Card: Metric-Name, Zielwert, aktueller Wert, Trend-Sparkline
- Farbe: Grün wenn Ziel erreicht, Orange wenn knapp, Rot wenn verfehlt
