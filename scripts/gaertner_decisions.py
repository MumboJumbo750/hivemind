"""Gärtner: Create decision records for Phase 6→7 transition."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import scripts.api_test as a

EPIC_P7_ID = "8ff39903-15f4-425b-8466-7cfc405301cf"

def mcp(tool, args):
    r = a.mcp_call(tool, args)
    if 'result' in r:
        try:
            return json.loads(r['result'][0]['text'])
        except:
            return r['result'][0]['text']
    return r

# Decision Record 1: Outbox Consumer Architecture
print("Creating Decision Records...")

dr1 = mcp('hivemind/create_decision_record', {
    'epic_id': EPIC_P7_ID,
    'decision': 'Separate Outbox-Consumer pro Direction statt einem generischen Consumer',
    'rationale': 'Phase F hat bewiesen dass peer_outbound seinen eigenen Consumer braucht (Ed25519-Signing, Hub-Relay-Fallback). Phase 7 ergänzt einen outbound-Consumer mit System-spezifischen Adaptern (YouTrack, Sentry). Ein generischer Consumer wäre zu komplex — jeder Direction-Typ hat eigene Auth, Retry- und Delivery-Logik. Drei separate Jobs: peer_outbound (Phase F), outbound (Phase 7), inbound-routing (Phase 7).',
})
print(f"  DR1 (Outbox Architecture): {json.dumps(dr1)[:200]}")

dr2 = mcp('hivemind/create_decision_record', {
    'epic_id': EPIC_P7_ID,
    'decision': 'pgvector Cosine-Similarity mit konfigurierbarem Threshold (Default 0.85) für Auto-Routing',
    'rationale': 'Alternative war regelbasiertes Routing (Keyword-Matching). pgvector-Similarity ist flexibler, braucht keine manuellen Regeln und nutzt die seit Phase 3 vorhandene Embedding-Infrastruktur. Threshold ist per API änderbar ohne Neustart. Bei Embedding-Service-Ausfall: Graceful Degradation zu [UNROUTED] statt Fehlschlag.',
})
print(f"  DR2 (Auto-Routing): {json.dumps(dr2)[:200]}")

dr3 = mcp('hivemind/create_decision_record', {
    'epic_id': EPIC_P7_ID,
    'decision': 'DLQ-Requeue setzt attempts auf 0 (frischer Retry-Zyklus) statt Weiterzählen',
    'rationale': 'Ein Requeue ist eine bewusste Admin-Aktion (z.B. nach Bug-Fix oder Netzwerk-Recovery). Weiterzählen der attempts würde den Eintrag sofort wieder in die DLQ schieben wenn der erste Retry fehlschlägt. Reset auf 0 gibt dem Eintrag einen vollständigen frischen Zyklus (5 Versuche mit Exponential Backoff).',
})
print(f"  DR3 (DLQ Requeue): {json.dumps(dr3)[:200]}")

dr4 = mcp('hivemind/create_decision_record', {
    'epic_id': EPIC_P7_ID,
    'decision': 'KPI-Werte stündlich gecacht statt Echtzeit-Aggregation pro Request',
    'rationale': 'KPI-Berechnung erfordert Aggregat-Queries über große Tabellen (tasks, mcp_invocations, decision_requests). Echtzeit pro Request wäre zu teuer. Stündlicher Cache hat dieselbe Granularität wie der SLA-Cron und reicht für KPI-Monitoring. Phase 8 ergänzt historische Zeitreihen via kpi_snapshots-Tabelle.',
})
print(f"  DR4 (KPI Caching): {json.dumps(dr4)[:200]}")

# Also create an Epic-Doc for Phase 7 with the technical context
print("\nCreating Epic-Doc for Phase 7 technical context...")
doc = mcp('hivemind/create_epic_doc', {
    'epic_id': EPIC_P7_ID,
    'title': 'Phase 7 — Technischer Kontext & Vorarbeiten',
    'content': """# Phase 7 — Technischer Kontext

## Bestehende Infrastruktur (aus Phase 1-6)

### Outbox-System (Phase F)
- `sync_outbox`-Tabelle mit direction, state, attempts, payload
- `sync_dead_letter`-Tabelle für fehlgeschlagene Entries
- Bestehender Consumer: `app/services/outbox_consumer.py` (nur `peer_outbound`)
- APScheduler-Job registriert in main.py
- Ed25519-Signing + Hub-Relay-Fallback implementiert

### Webhook-Ingest (Phase 3)
- Endpoints: `POST /api/webhooks/youtrack`, `POST /api/webhooks/sentry` 
- HMAC-SHA256-Signaturvalidierung
- Payload-Normalisierung + Idempotenz via idempotency_key
- Schreibt `direction='inbound'` in sync_outbox

### Embedding-Service (Phase 3)
- `app/services/embedding_service.py` mit OllamaProvider
- Circuit-Breaker mit adaptivem Backoff
- HNSW-Indexes auf skills, wiki_articles, epics
- Graceful Degradation bei Ollama-Ausfall (NULL-Embeddings)

### Triage (Phase 3+6)
- `app/services/triage_service.py` mit route_event/ignore_event
- SSE-Events: triage_routed, triage_escalated
- SLA-Cron + Backup-Owner-Eskalation (Phase 6)
- Routing-States: unrouted/routed/ignored/escalated

### Nexus Grid (Phase 5)
- Cytoscape.js 2D Graph mit Cola-Layout
- code_nodes + code_edges Tabellen
- Fog-of-War: explored_at-Timestamp

## Phase 7 muss ergänzen
1. **outbound-Consumer** — analog zu peer_outbound, aber für YouTrack/Sentry
2. **Exponential Backoff** — `next_retry_at = now() + 2^attempts * 60s`
3. **pgvector Auto-Routing** — inbound Events → Epic via Cosine-Similarity
4. **Bug-Aggregation** — Sentry Stack-Traces → node_bug_reports
5. **DLQ-MCP-Tools** — requeue_dead_letter, discard_dead_letter
6. **Bug Heatmap** — Nexus Grid Layer mit node_bug_reports.count
7. **KPI-Dashboard** — 6 Kern-KPIs mit stündlichem Cache
8. **Sync-Status-Panel** — Queue-Größen + Fehler-Übersicht in Settings
""",
})
print(f"  Epic-Doc: {json.dumps(doc)[:200]}")

print("\nDecision records and epic doc created!")
