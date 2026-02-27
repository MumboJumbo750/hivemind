# Observability — Logging, Metrics & Tracing

← [Index](../../masterplan.md)

**Aktiv ab:** Phase 1 (strukturiertes Logging); Phase 3+ (Metrics & Tracing optional)

---

## Philosophie

Observability in Hivemind folgt drei Prinzipien:

1. **Logs als primäre Quelle** — Jede bedeutsame State-Änderung wird geloggt. Kein Fire-and-Forget.
2. **Kein Silent Failure** — Fehler werden immer geloggt, auch wenn sie recoverable sind. Besonders Embedding-Failures, DLQ-Einträge und Federation-Sync-Fehler.
3. **Operational Simplicity** — Phase 1–7: Structured JSON-Logs reichen. Kein obligatorisches Prometheus/OTEL. Optional, aber vorbereitet.

---

## Logging

### Log-Levels

| Level | Verwendung | Beispiele |
| --- | --- | --- |
| `DEBUG` | Interne Programmflüsse, nur in Entwicklung | SQL-Query-Params, Embedding-Dimensionen, Routing-Entscheidungen |
| `INFO` | Bedeutsame State-Änderungen im normalen Betrieb | Task-Transition, Epic created, Skill merged, Peer connected |
| `WARNING` | Unerwartete Zustände, aber System läuft weiter | Embedding-Queue voll, Circuit Breaker HALF-OPEN, Peer timeout |
| `ERROR` | Operationale Fehler — erfordert Admin-Aufmerksamkeit | DLQ-Eintrag, Federation-401, DB-Constraint-Violation |
| `CRITICAL` | System kann nicht normal weiterarbeiten | DB-Connection-Pool erschöpft, Key-Passphrase falsch, Startup-Fehler |

**Default Log-Level:**
- `PRODUCTION`: `INFO`
- `DEVELOPMENT` (env `HIVEMIND_ENV=development`): `DEBUG`

### Structured Log Format

Alle Logs als JSON-Lines (ein JSON-Objekt pro Zeile):

```json
{
  "timestamp": "2026-02-27T14:32:01.123Z",
  "level": "INFO",
  "logger": "hivemind.tasks.state_machine",
  "event": "task_state_changed",
  "task_id": "uuid-here",
  "task_key": "TASK-88",
  "epic_key": "EPIC-12",
  "old_state": "in_progress",
  "new_state": "in_review",
  "actor_id": "uuid-here",
  "actor_role": "developer",
  "duration_ms": 45
}
```

**Pflichtfelder in jedem Log-Eintrag:**

| Feld | Typ | Beschreibung |
| --- | --- | --- |
| `timestamp` | ISO 8601 UTC | Zeitpunkt des Events |
| `level` | string | Log-Level |
| `logger` | string | Python-Logger-Name (dotted) |
| `event` | string | Maschinenlesbarer Event-Name (snake_case) |

**Optionale aber empfohlene Felder:**

| Feld | Wann |
| --- | --- |
| `request_id` | Bei HTTP-Request-Kontext |
| `actor_id`, `actor_role` | Bei autorisierten Aktionen |
| `task_key`, `epic_key` | Bei Task/Epic-Operationen |
| `node_id` | Bei Federation-Operationen |
| `duration_ms` | Bei DB-Queries und externen Calls |
| `error` | Bei ERROR/CRITICAL (Exception-Message) |
| `traceback` | Bei unerwarteten Exceptions |

### Pflicht-Events

Diese Events **müssen** immer geloggt werden:

| Event | Level | Logger |
| --- | --- | --- |
| Task-State-Transition | INFO | `hivemind.tasks.state_machine` |
| Epic-State-Transition (auto) | INFO | `hivemind.epics.state_machine` |
| Skill lifecycle change | INFO | `hivemind.skills.lifecycle` |
| Guard execution result | INFO | `hivemind.guards.executor` |
| Decision Request created/resolved/expired | INFO | `hivemind.decision_requests` |
| Escalation triggered/resolved | WARNING | `hivemind.escalation` |
| MCP Tool call (eingehend) | INFO | `hivemind.mcp.handler` |
| Federation message sent | INFO | `hivemind.federation.outbox` |
| Federation message received | INFO | `hivemind.federation.handler` |
| Federation signature validation failed | ERROR | `hivemind.federation.auth` |
| Sync Outbox retry | WARNING | `hivemind.sync.outbox` |
| DLQ entry created | ERROR | `hivemind.sync.dlq` |
| Embedding calculation failed | WARNING | `hivemind.embeddings` |
| Circuit Breaker state change | WARNING | `hivemind.embeddings.circuit_breaker` |
| Peer online/offline | INFO | `hivemind.federation.heartbeat` |
| API authentication failure | WARNING | `hivemind.auth` |
| DB query > 1000ms | WARNING | `hivemind.db.slow_query` |

### Konfiguration

```bash
HIVEMIND_LOG_LEVEL=INFO            # DEBUG | INFO | WARNING | ERROR | CRITICAL
HIVEMIND_LOG_FORMAT=json           # json | text (text nur für Entwicklung)
HIVEMIND_LOG_FILE=                 # leer = stdout (Docker-Standard); Pfad = Datei-Output
HIVEMIND_LOG_SQL=false             # true = SQLAlchemy SQL-Queries loggen (DEBUG-Modus)
HIVEMIND_SLOW_QUERY_THRESHOLD_MS=1000  # Queries über diesem Wert werden als WARNING geloggt
```

---

## Prometheus Metrics (Optional, ab Phase 3)

Aktivierung: `HIVEMIND_METRICS_ENABLED=true` → Endpoint `GET /metrics` (Prometheus-Format).

### Basis-Metriken

```
# HELP hivemind_tasks_total Anzahl Tasks nach finalem State
# TYPE hivemind_tasks_total counter
hivemind_tasks_total{state="done"}
hivemind_tasks_total{state="cancelled"}
hivemind_tasks_total{state="escalated"}

# HELP hivemind_tasks_in_flight Aktuelle Tasks nach State
# TYPE hivemind_tasks_in_flight gauge
hivemind_tasks_in_flight{state="in_progress"}
hivemind_tasks_in_flight{state="in_review"}
hivemind_tasks_in_flight{state="blocked"}

# HELP hivemind_task_duration_seconds Zeit von ready bis done
# TYPE hivemind_task_duration_seconds histogram
hivemind_task_duration_seconds_bucket{le="3600"}    # < 1h
hivemind_task_duration_seconds_bucket{le="86400"}   # < 1d
hivemind_task_duration_seconds_bucket{le="+Inf"}

# HELP hivemind_qa_failed_count qa_failed-Events pro Task (Histogram)
# TYPE hivemind_qa_failed_count histogram
hivemind_qa_failed_count_bucket{le="0"}
hivemind_qa_failed_count_bucket{le="1"}
hivemind_qa_failed_count_bucket{le="2"}
hivemind_qa_failed_count_bucket{le="3"}
```

### API-Metriken

```
# HELP hivemind_http_requests_total HTTP-Anfragen nach Endpoint und Status
# TYPE hivemind_http_requests_total counter
hivemind_http_requests_total{method="POST",endpoint="/api/tasks/{id}/state",status="200"}
hivemind_http_requests_total{method="POST",endpoint="/api/tasks/{id}/state",status="409"}

# HELP hivemind_http_request_duration_seconds Antwortzeiten nach Endpoint
# TYPE hivemind_http_request_duration_seconds histogram
hivemind_http_request_duration_seconds_bucket{endpoint="/api/tasks/{id}/state",le="0.1"}
hivemind_http_request_duration_seconds_bucket{endpoint="/api/tasks/{id}/state",le="0.5"}
```

### Federation-Metriken

```
# HELP hivemind_federation_sync_total Sync-Operationen nach Direction und Ergebnis
# TYPE hivemind_federation_sync_total counter
hivemind_federation_sync_total{direction="peer_outbound",result="success"}
hivemind_federation_sync_total{direction="peer_outbound",result="retry"}
hivemind_federation_sync_total{direction="peer_outbound",result="dlq"}

# HELP hivemind_federation_peers_active Anzahl aktiver Peers
# TYPE hivemind_federation_peers_active gauge
hivemind_federation_peers_active

# HELP hivemind_outbox_queue_depth Länge der Outbox nach Direction
# TYPE hivemind_outbox_queue_depth gauge
hivemind_outbox_queue_depth{direction="peer_outbound"}
hivemind_outbox_queue_depth{direction="outbound"}     # YouTrack/Sentry
```

### Embedding-Metriken

```
# HELP hivemind_embedding_queue_depth Ausstehende Embedding-Berechnungen
# TYPE hivemind_embedding_queue_depth gauge
hivemind_embedding_queue_depth

# HELP hivemind_embedding_duration_seconds Embedding-Berechnungszeit
# TYPE hivemind_embedding_duration_seconds histogram
hivemind_embedding_duration_seconds_bucket{le="1"}
hivemind_embedding_duration_seconds_bucket{le="5"}

# HELP hivemind_circuit_breaker_state Circuit-Breaker-State für Ollama
# TYPE hivemind_circuit_breaker_state gauge
hivemind_circuit_breaker_state{service="ollama"}  # 0=CLOSED, 1=HALF_OPEN, 2=OPEN
```

---

## OpenTelemetry Tracing (Optional, ab Phase 7)

Aktivierung: `HIVEMIND_OTEL_ENABLED=true` + `HIVEMIND_OTEL_ENDPOINT=http://jaeger:4317`.

Instrumentierte Spans:

| Span | Attribute |
| --- | --- |
| `http.server` (jede FastAPI-Route) | `http.method`, `http.url`, `http.status_code` |
| `db.query` (jede SQLAlchemy-Query) | `db.statement` (ohne Parameter), `db.duration_ms` |
| `task.state_transition` | `task.key`, `old_state`, `new_state`, `actor_role` |
| `embedding.calculate` | `entity_type`, `provider`, `model`, `dimension` |
| `federation.send` | `target_node_id`, `entity_type`, `attempt` |
| `mcp.tool_call` | `tool_name`, `actor_role` |

> **Datenschutz:** DB-Statement-Spans enthalten **niemals** Query-Parameter (keine User-Daten in Traces). Nur Statement-Template mit Platzhaltern (`$1`, `$2`).

### Docker Compose Integration (Optional)

```yaml
# docker-compose.observability.yml — optional einbinden
services:
  jaeger:
    image: jaegertracing/all-in-one:1.55
    ports:
      - "16686:16686"   # Jaeger UI
      - "4317:4317"     # OTLP gRPC
    environment:
      COLLECTOR_OTLP_ENABLED: "true"

  prometheus:
    image: prom/prometheus:v2.50.0
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:10.3.0
    ports:
      - "3001:3000"
    volumes:
      - ./config/grafana:/etc/grafana/provisioning:ro
```

```yaml
# config/prometheus.yml
scrape_configs:
  - job_name: hivemind
    static_configs:
      - targets: ["backend:8000"]
    metrics_path: /metrics
    scrape_interval: 15s
```

---

## Health Check Endpoint

`GET /health` — immer verfügbar, keine Auth:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "checks": {
    "database": "ok",
    "ollama": "ok",
    "federation": "ok",
    "outbox_depth": 3
  },
  "timestamp": "2026-02-27T14:32:01Z"
}
```

| Check | Wert | Bedeutung |
| --- | --- | --- |
| `database` | `ok` / `error` | DB-Connection-Pool-Ping |
| `ollama` | `ok` / `degraded` / `error` / `disabled` | Ollama-Health (Circuit-Breaker-State) |
| `federation` | `ok` / `disabled` | Federation aktiv + mind. 1 Peer erreichbar |
| `outbox_depth` | Integer | Anzahl ausstehender Outbox-Einträge |

HTTP-Status: `200` wenn `database=ok`, `503` sonst. Frontend zeigt bei 503 ein Warning-Banner.

---

## Konfiguration — Vollständige Referenz

| Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_LOG_LEVEL` | `INFO` | Log-Level |
| `HIVEMIND_LOG_FORMAT` | `json` | `json` oder `text` |
| `HIVEMIND_LOG_FILE` | `` (stdout) | Pfad für File-Output |
| `HIVEMIND_LOG_SQL` | `false` | SQLAlchemy-Queries loggen |
| `HIVEMIND_SLOW_QUERY_THRESHOLD_MS` | `1000` | Schwellwert für Slow-Query-Warning |
| `HIVEMIND_METRICS_ENABLED` | `false` | Prometheus-Metrics aktivieren |
| `HIVEMIND_OTEL_ENABLED` | `false` | OpenTelemetry-Tracing aktivieren |
| `HIVEMIND_OTEL_ENDPOINT` | `` | OTLP-Endpoint (z.B. `http://jaeger:4317`) |
| `HIVEMIND_OTEL_SERVICE_NAME` | `hivemind` | Service-Name in Traces |
