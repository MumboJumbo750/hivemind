---
title: pgvector Auto-Routing (Event→Epic Zuordnung)
service_scope:
- backend
stack:
- python
- sqlalchemy
- pgvector
- ollama
confidence: 0.5
source_epics:
- EPIC-PHASE-7
---

## Skill: pgvector Auto-Routing (Event→Epic Zuordnung)

### Rolle
Du implementierst das automatische Routing von inbound-Events zu Epics basierend auf pgvector Cosine-Similarity. Dies ist der erste echte Auto-Routing-Schritt in Hivemind (Phase 7).

### Konventionen
- Service: `app/services/routing_service.py`
- Trigger: Inbound-Event wird empfangen → Embedding berechnen → Similarity vs. Epic-Embeddings
- Threshold: `app_settings.routing_threshold` (Default: 0.85)
- `>= threshold` → auto-assign: `routing_state = 'routed'`, `routed_to_epic_id` gesetzt
- `< threshold` → `routing_state = 'unrouted'` → Triage Station
- Admin kann Threshold ändern: `PATCH /api/settings/routing_threshold` (Laufzeit, kein Neustart)
- Env-Override: `HIVEMIND_ROUTING_THRESHOLD`
- Embedding-Input: `title + description + (stack_trace_summary bei Sentry)`

### Routing-Service

```python
from app.services.embedding_service import get_embedding

async def auto_route_event(db: AsyncSession, event: SyncOutbox) -> bool:
    threshold = await get_routing_threshold(db)
    
    # Embedding für das Event berechnen
    text = f"{event.payload.get('summary', '')} {event.payload.get('description', '')}"
    event_embedding = await get_embedding(text)
    
    if event_embedding is None:
        return False  # Embedding-Service nicht verfügbar → manuell
    
    # Cosine-Similarity gegen alle aktiven Epic-Embeddings
    result = await db.execute(text('''
        SELECT id, epic_key, title, 
               1 - (embedding <=> :query) AS similarity
        FROM epics
        WHERE embedding IS NOT NULL AND state IN ('scoped', 'active')
        ORDER BY embedding <=> :query
        LIMIT 1
    '''), {"query": str(event_embedding)})
    
    best = result.first()
    if best and best.similarity >= threshold:
        event.routing_state = "routed"
        event.routed_to_epic_id = best.id
        event.routing_confidence = best.similarity
        return True
    
    return False  # Bleibt [UNROUTED]
```

### Threshold-API

```python
@router.patch("/api/settings/routing_threshold")
async def update_threshold(value: float = Body(..., ge=0.0, le=1.0), db=Depends(get_db)):
    settings = await get_app_settings(db)
    settings.routing_threshold = value
    await db.commit()
    return {"routing_threshold": value}
```

### Wichtig
- Embedding-Service nicht verfügbar → Graceful Degradation: Event bleibt [UNROUTED]
- Confidence wird auf dem Event gespeichert (`routing_confidence`) für KPI-Tracking
- KPI: Routing-Precision >= 85% nach 2 Wochen Betrieb
- Embedding-Neuberechnung nötig wenn Embedding-Provider gewechselt wird
