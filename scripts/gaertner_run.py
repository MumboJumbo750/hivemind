"""Gärtner-Lauf: Neue Skills für Phase 7 anlegen und bestehende verbessern.

Destilliert aus:
- Phase F: Outbox-Consumer (peer_outbound) erfolgreich implementiert
- Phase 3: Webhook-Ingest, Ollama-Embeddings, pgvector-Suche
- Phase 5: Nexus Grid 2D, Wiki CRUD
- Phase 6: Eskalation, SLA-Cron, Decision Requests, Triage
- Quellcode-Analyse: backend/app/services/outbox_consumer.py, routers, models
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.api_test as a

PROJECT_ID = "e457a4c2-df57-475b-a37e-d10ca794f62f"
EPIC_P7_ID = "8ff39903-15f4-425b-8466-7cfc405301cf"

def mcp(tool, args):
    r = a.mcp_call(tool, args)
    if 'result' in r:
        text = r['result'][0]['text']
        try:
            return json.loads(text)
        except:
            return text
    return r

def propose_and_submit(title, content, scope, stack, confidence):
    """Propose a skill and submit it for merge."""
    print(f"\n--- Proposing: {title} ---")
    r = mcp('hivemind/propose_skill', {
        'title': title,
        'content': content,
        'service_scope': scope,
        'stack': stack,
    })
    print(f"  propose_skill -> {json.dumps(r)[:200]}")
    
    if isinstance(r, dict) and 'data' in r:
        skill_id = r['data'].get('id')
        if skill_id:
            # Submit for merge
            r2 = mcp('hivemind/submit_skill_proposal', {'skill_id': skill_id})
            print(f"  submit -> {json.dumps(r2)[:200]}")
            # Merge directly (we're admin in solo mode)
            r3 = mcp('hivemind/merge_skill', {'skill_id': skill_id})
            print(f"  merge -> {json.dumps(r3)[:200]}")
            return skill_id
    return None


# ============================================================
# NEUE SKILLS FÜR PHASE 7
# ============================================================

# 1. DLQ-Management (Dead Letter Queue)
propose_and_submit(
    title="DLQ-Management (Dead Letter Queue)",
    content="""## Skill: DLQ-Management (Dead Letter Queue)

### Rolle
Du implementierst DLQ-Verwaltung für fehlgeschlagene Outbox-Einträge im Hivemind-Backend. Dead Letters entstehen wenn ein Outbox-Consumer nach max_attempts (Default: 5) scheitert.

### Konventionen
- Tabelle: `sync_dead_letter` — persistiert fehlgeschlagene Events mit vollem Payload
- Felder: `outbox_id`, `system`, `entity_type`, `entity_id`, `payload`, `error`, `created_at`
- Requeue: Dead Letter → zurück in `sync_outbox` mit `state='pending'`, `attempts=0`
- Discard: Dead Letter → `state='discarded'` (soft-delete, bleibt für Audit)
- MCP-Tools: `hivemind/requeue_dead_letter`, `hivemind/discard_dead_letter`
- REST-Alias: `POST /api/triage/dead-letters/{id}/requeue`, `POST /api/triage/dead-letters/{id}/discard`
- Permission: `admin` oder `triage` Rolle
- Jede DLQ-Aktion wird in `mcp_invocations` geloggt (Audit)
- SSE-Event bei DLQ-Änderung: `triage_dlq_updated`

### DLQ-Eintrag anlegen (im Outbox-Consumer)

```python
async def _move_to_dlq(db: AsyncSession, entry: SyncOutbox, error: str) -> None:
    dead_letter = SyncDeadLetter(
        outbox_id=entry.id,
        system=entry.system,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        payload=entry.payload,
        error=error,
    )
    db.add(dead_letter)
    entry.state = "dead_letter"
```

### Requeue-Service

```python
async def requeue_dead_letter(db: AsyncSession, dead_letter_id: UUID) -> dict:
    dl = await db.get(SyncDeadLetter, dead_letter_id)
    if not dl:
        raise HTTPException(404, "Dead letter not found")
    
    new_entry = SyncOutbox(
        direction=dl.direction or "outbound",
        system=dl.system,
        entity_type=dl.entity_type,
        entity_id=dl.entity_id,
        payload=dl.payload,
        state="pending",
        attempts=0,
    )
    db.add(new_entry)
    dl.state = "requeued"
    dl.requeued_at = datetime.utcnow()
    await db.commit()
    return {"status": "requeued", "new_outbox_id": str(new_entry.id)}
```

### Wichtig
- DLQ-Payloads enthalten den vollständigen Original-Payload (kein Datenverlust)
- Requeue setzt attempts auf 0 (frischer Retry-Zyklus)
- Discard ist soft-delete — Eintrag bleibt in der DB für Audit
- Frontend zeigt DLQ-Items in der Triage Station unter [DEAD LETTER]-Kategorie
- DLQ-Count wird im Sync-Status-Panel in Settings angezeigt""",
    scope=["backend"],
    stack=["python", "fastapi", "sqlalchemy", "postgresql"],
    confidence=0.85,
)

# 2. Outbound-Sync (YouTrack/Sentry)
propose_and_submit(
    title="Outbound-Sync (YouTrack/Sentry Status-Rücksync)",
    content="""## Skill: Outbound-Sync (YouTrack/Sentry Status-Rücksync)

### Rolle
Du implementierst den outbound Sync-Consumer für die Rücksynchronisierung von Hivemind-Status-Änderungen an externe Systeme (YouTrack, Sentry). Phase 7 ergänzt den in Phase F implementierten peer_outbound-Consumer um einen outbound-Consumer.

### Konventionen
- Consumer verarbeitet `sync_outbox` mit `direction='outbound'`
- APScheduler-Job analog zum peer_outbound Consumer
- `next_retry_at = now() + 2^attempts * 60s` (Exponential Backoff)
- Nach `attempts >= HIVEMIND_DLQ_MAX_ATTEMPTS (5)` → `sync_dead_letter`
- Separate Client-Adapter pro System:
  - `YouTrackSyncAdapter`: Status-Updates + Assignee rücksyncen via YouTrack REST API
  - `SentrySyncAdapter`: Bug-Report-Aggregation in `node_bug_reports`

### Outbound-Consumer (erweitert bestehenden outbox_consumer.py)

```python
EVENT_TYPE_TO_ADAPTER = {
    "youtrack_status_sync": YouTrackSyncAdapter,
    "sentry_bug_aggregate": SentrySyncAdapter,
}

async def process_outbound():
    async with AsyncSessionLocal() as db:
        entries = await db.execute(
            select(SyncOutbox)
            .where(
                SyncOutbox.direction == "outbound",
                SyncOutbox.state == "pending",
                SyncOutbox.attempts < settings.hivemind_dlq_max_attempts,
            )
            .order_by(SyncOutbox.created_at.asc())
            .limit(BATCH_SIZE)
        )
        for entry in entries.scalars():
            adapter_cls = EVENT_TYPE_TO_ADAPTER.get(entry.entity_type)
            if not adapter_cls:
                logger.warning("Unknown outbound type: %s", entry.entity_type)
                entry.attempts += 1
                continue
            try:
                adapter = adapter_cls(settings)
                await adapter.sync(entry)
                await db.delete(entry)
            except Exception as exc:
                entry.attempts += 1
                entry.next_retry_at = datetime.utcnow() + timedelta(
                    seconds=2 ** entry.attempts * 60
                )
                if entry.attempts >= settings.hivemind_dlq_max_attempts:
                    await _move_to_dlq(db, entry, str(exc))
        await db.commit()
```

### YouTrack-Adapter

```python
class YouTrackSyncAdapter:
    def __init__(self, settings):
        self.base_url = settings.youtrack_url
        self.token = settings.youtrack_api_token

    async def sync(self, entry: SyncOutbox):
        issue_id = entry.payload["external_id"]
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.base_url}/api/issues/{issue_id}",
                json={"state": entry.payload["state"]},
                headers={"Authorization": f"Bearer {self.token}"},
            )
```

### Wichtig
- `direction='outbound'` ist für externe Systeme (YouTrack, Sentry)
- `direction='peer_outbound'` ist für Federation (existiert seit Phase F)
- Beide Consumer laufen als separate APScheduler-Jobs
- Exponential Backoff: `2^attempts * 60s` (1min, 2min, 4min, 8min, 16min)
- Env-Variablen: `HIVEMIND_YOUTRACK_URL`, `HIVEMIND_YOUTRACK_API_TOKEN`, `HIVEMIND_SENTRY_API_TOKEN`""",
    scope=["backend"],
    stack=["python", "fastapi", "sqlalchemy", "httpx"],
    confidence=0.80,
)

# 3. pgvector Auto-Routing
propose_and_submit(
    title="pgvector Auto-Routing (Event→Epic Zuordnung)",
    content="""## Skill: pgvector Auto-Routing (Event→Epic Zuordnung)

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
- Embedding-Neuberechnung nötig wenn Embedding-Provider gewechselt wird""",
    scope=["backend"],
    stack=["python", "sqlalchemy", "pgvector", "ollama"],
    confidence=0.85,
)

# 4. Sentry-Bug-Aggregation & node_bug_reports
propose_and_submit(
    title="Sentry-Bug-Aggregation (node_bug_reports)",
    content="""## Skill: Sentry-Bug-Aggregation (node_bug_reports)

### Rolle
Du implementierst die Aggregation von Sentry-Bug-Reports in der `node_bug_reports`-Tabelle. Die Daten fließen in die Bug Heatmap des Nexus Grid.

### Konventionen
- Tabelle: `node_bug_reports` (existiert seit Phase 1a Schema)
  - `code_node_id` — Referenz auf den Code-Node im Nexus Grid
  - `count` — Anzahl Bug-Reports für diesen Node
  - `last_seen` — Zeitstempel des letzten Bug-Reports
  - `severity` — Aggregierte Severity (critical/warning/info)
  - `sentry_issue_ids` — JSON-Array der verknüpften Sentry-Issue-IDs
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
            select(NodeBugReport).where(NodeBugReport.code_node_id == code_node.id)
        )
        bug = existing.scalar_one_or_none()
        if bug:
            bug.count += 1
            bug.last_seen = datetime.utcnow()
            if sentry_id not in (bug.sentry_issue_ids or []):
                bug.sentry_issue_ids = (bug.sentry_issue_ids or []) + [sentry_id]
        else:
            bug = NodeBugReport(
                code_node_id=code_node.id,
                count=1,
                severity=severity,
                last_seen=datetime.utcnow(),
                sentry_issue_ids=[sentry_id],
            )
            db.add(bug)
```

### Wichtig
- `node_bug_reports.count` steuert Knotengröße und -farbe in der Bug Heatmap
- Hover im Nexus Grid zeigt Bug-Details (Severity, Count, letzte Issue-IDs)
- MCP-Tool: `hivemind/assign_bug` für manuelles Bug→Epic Routing
- Stack-Trace-Pfade sind relativ — Fuzzy-Matching gegen `code_nodes.path` nötig""",
    scope=["backend"],
    stack=["python", "sqlalchemy", "postgresql"],
    confidence=0.80,
)

# 5. KPI-Dashboard Backend (Aggregation & API)
propose_and_submit(
    title="KPI-Aggregation & Dashboard-API",
    content="""## Skill: KPI-Aggregation & Dashboard-API

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
- Farbe: Grün wenn Ziel erreicht, Orange wenn knapp, Rot wenn verfehlt""",
    scope=["backend", "frontend"],
    stack=["python", "fastapi", "sqlalchemy", "postgresql", "typescript", "vue3"],
    confidence=0.85,
)

# 6. Bug Heatmap Layer (Nexus Grid Erweiterung)
propose_and_submit(
    title="Nexus Grid Bug-Heatmap Layer",
    content="""## Skill: Nexus Grid Bug-Heatmap Layer

### Rolle
Du erweiterst das bestehende Cytoscape.js Nexus Grid (2D Graph) um einen Bug-Heatmap-Layer. Knotengröße und -farbe werden nach `node_bug_reports.count` skaliert.

### Konventionen
- Datenquelle: `GET /api/nexus/graph` erweitert um `bug_count` und `bug_severity` pro Node
- Cytoscape-Styling:
  - Knotengröße: `Math.min(20 + bug_count * 3, 80)` px
  - Knotenfarbe: Gradient von `--color-success` (0 bugs) → `--color-warning` (1-5) → `--color-danger` (6+)
  - Opacity: `Math.min(0.4 + bug_count * 0.1, 1.0)`
- Hover: Bug-Details-Panel zeigt Severity, Count, letzte Sentry-Issue-IDs
- Toggle: Heatmap-Layer ein/ausschaltbar über Toolbar-Button
- Performance: Nur Nodes mit `bug_count > 0` bekommen Heatmap-Styling

### Cytoscape-Style-Extension

```typescript
function bugHeatmapStyle(bugCount: number, severity: string): Partial<cytoscape.Css.Node> {
  const size = Math.min(20 + bugCount * 3, 80)
  const color = severity === 'critical' 
    ? 'var(--color-danger)' 
    : severity === 'warning' 
      ? 'var(--color-warning)' 
      : 'var(--color-info)'
  
  return {
    width: size,
    height: size,
    'background-color': bugCount > 0 ? color : 'var(--color-node-default)',
    'background-opacity': Math.min(0.4 + bugCount * 0.1, 1.0),
    'border-width': bugCount > 5 ? 3 : 1,
    'border-color': bugCount > 5 ? 'var(--color-danger)' : 'var(--color-border)',
  }
}
```

### Hover-Panel

```vue
<template>
  <div v-if="selectedNode?.bugCount > 0" class="bug-detail-panel">
    <h4>Bug Report: {{ selectedNode.label }}</h4>
    <div class="stat">Count: {{ selectedNode.bugCount }}</div>
    <div class="stat">Severity: {{ selectedNode.bugSeverity }}</div>
    <div class="stat">Last seen: {{ formatDate(selectedNode.bugLastSeen) }}</div>
    <ul>
      <li v-for="id in selectedNode.sentryIssueIds" :key="id">{{ id }}</li>
    </ul>
  </div>
</template>
```

### Wichtig
- Heatmap-Layer ist optional (Toggle) — Default: aus, damit Nexus Grid performant bleibt
- Performance-Budget: Nexus Grid + Heatmap muss unter 16ms pro Frame bleiben
- Bug-Daten werden nur geladen wenn Layer aktiv ist (lazy loading)
- Design Tokens: Nutze bestehende Semantic Tokens (`--color-danger`, `--color-warning`)""",
    scope=["frontend"],
    stack=["typescript", "vue3", "cytoscape"],
    confidence=0.80,
)

# 7. Triage DLQ-View (Frontend)
propose_and_submit(
    title="Triage Station DLQ-Kategorie (Frontend)",
    content="""## Skill: Triage Station DLQ-Kategorie (Frontend)

### Rolle
Du erweiterst die Triage Station View um eine `[DEAD LETTER]`-Kategorie. Dead Letters sind fehlgeschlagene Outbox-Einträge die nach max_attempts in die DLQ verschoben wurden.

### Konventionen
- Neue Tab/Kategorie in Triage Station: `[DEAD LETTER]`
- Datenstrom: SSE-Event `triage_dlq_updated` triggert Refresh
- API: `GET /api/sync-outbox?state=dead_letter` oder dedizierter DLQ-Endpoint
- Aktionen pro DLQ-Item:
  - "Erneut versuchen" → `POST /api/triage/dead-letters/{id}/requeue` (oder MCP-Tool)
  - "Verwerfen" → `POST /api/triage/dead-letters/{id}/discard`
- Detail-Ansicht: Fehler-Nachricht, Payload, Timestamps, Attempt-History

### DLQ-Liste

```vue
<template>
  <div class="dlq-list">
    <div v-for="item in deadLetters" :key="item.id" class="dlq-item">
      <div class="dlq-header">
        <span class="badge badge-danger">DLQ</span>
        <span class="entity-type">{{ item.entity_type }}</span>
        <span class="system">{{ item.system }}</span>
        <time>{{ formatDate(item.created_at) }}</time>
      </div>
      <div class="dlq-error">{{ item.error }}</div>
      <div class="dlq-actions">
        <HivemindButton variant="secondary" @click="requeue(item.id)">
          Erneut versuchen
        </HivemindButton>
        <HivemindButton variant="ghost" @click="discard(item.id)">
          Verwerfen
        </HivemindButton>
      </div>
    </div>
  </div>
</template>
```

### Wichtig
- DLQ-Count wird als Badge auf dem Triage-Tab angezeigt (Attention-Indikator)
- Requeue setzt den Dead Letter zurück in sync_outbox mit attempts=0
- Discard ist ein Soft-Delete (bleibt in DB für Audit)
- Error-Details sind expandable (Klick zeigt Full Payload + Stack Trace)""",
    scope=["frontend"],
    stack=["typescript", "vue3"],
    confidence=0.80,
)

# 8. Sync-Status-Panel (Frontend)
propose_and_submit(
    title="Sync-Status-Panel (Settings View)",
    content="""## Skill: Sync-Status-Panel (Settings View)

### Rolle
Du implementierst ein Sync-Status-Panel in der Settings View. Es zeigt den Zustand der Outbox-Queue, letzte erfolgreiche Syncs und fehlgeschlagene Syncs.

### Konventionen
- Platzierung: Settings View, eigene Sektion/Tab "Sync Status"
- Daten: `GET /api/sync-outbox?limit=10` + Aggregat-Endpoint für Queue-Größe
- Refresh: Auto-Refresh alle 30s oder manueller Refresh-Button
- Drei Bereiche:
  1. **Queue-Status**: Outbox-Größe pro Direction (outbound, peer_outbound, inbound)
  2. **Letzte Syncs**: Erfolgreiche deliveries (Timestamp, Target, Type)
  3. **Fehlgeschlagen**: Aktuelle Retry-Items + DLQ-Count

### Panel-Struktur

```vue
<template>
  <section class="sync-status-panel">
    <h3>Sync Status</h3>
    
    <!-- Queue-Sizes -->
    <div class="queue-grid">
      <SyncQueueCard label="Outbound" :count="queueSizes.outbound" />
      <SyncQueueCard label="Federation" :count="queueSizes.peer_outbound" />
      <SyncQueueCard label="Inbound" :count="queueSizes.inbound" />
      <SyncQueueCard label="Dead Letters" :count="queueSizes.dead_letter" variant="danger" />
    </div>
    
    <!-- Recent Syncs -->
    <h4>Letzte erfolgreiche Syncs</h4>
    <ul class="sync-list">
      <li v-for="s in recentSyncs" :key="s.id">
        {{ s.entity_type }} → {{ s.target }} ({{ formatTimeAgo(s.completed_at) }})
      </li>
    </ul>
    
    <!-- Failed -->
    <h4>Fehlgeschlagene Syncs</h4>
    <ul class="sync-list sync-list--errors">
      <li v-for="f in failedSyncs" :key="f.id">
        {{ f.entity_type }} — Attempt {{ f.attempts }}/{{ maxAttempts }}
        <span class="error">{{ f.error }}</span>
      </li>
    </ul>
  </section>
</template>
```

### Wichtig
- Queue-Count von 0 = alles synchron → grüner Status-Indikator
- DLQ-Count > 0 → roter Badge + Link zu Triage Station
- Panel ist readonly — Aktionen (Requeue, Discard) nur über Triage Station""",
    scope=["frontend"],
    stack=["typescript", "vue3"],
    confidence=0.75,
)

print("\n\n=== Neue Skills angelegt ===")
print("Fertig! Jetzt werden existierende Skills verbessert...")
