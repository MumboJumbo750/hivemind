# Externe Sync — Outbox & Dead Letter Queue

← [Index](../../masterplan.md)

---

## Source-of-Truth Matrix

| Feld | Source of Truth | Hivemind-Verhalten |
| --- | --- | --- |
| `task.state` | Hivemind | Maßgeblich |
| `youtrack.issue.summary/description` | YouTrack | Hivemind cached |
| `youtrack.issue.assignee` | Hivemind Owner-Routing | Rücksync zu YouTrack |
| `sentry.event.exception` | Sentry | Append-only in Hivemind, nie mutieren |

---

## Konfliktregeln

1. Ältere Updates werden verworfen (Provider-Timestamp + Revision/Version, falls vorhanden)
2. Bei Gleichstand gewinnt definierte SoT-Seite
3. Jeder externe Write läuft über Outbox mit Retry und Dead-Letter Queue

---

## Outbox Pattern

Alle externen Sync-Operationen (Ingest + Rücksync) laufen über die `sync_outbox`.
Die Richtung ist explizit über `direction` getrennt:

- `inbound` = externe Events kommen in Hivemind an (Webhook-Ingest)
- `outbound` = Hivemind schreibt Updates zurück in externe Systeme (YouTrack, Sentry)
- `peer_outbound` = Hivemind sendet Federation-Nachricht an Peer-Node
- `peer_inbound` = Hivemind hat Nachricht von Peer-Node empfangen (Audit-Trail)

```sql
CREATE TABLE sync_outbox (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  dedup_key     TEXT UNIQUE,          -- Idempotenz je externes Ereignis (z.B. "youtrack:event:1718036400:ISSUE-42")
  direction      TEXT NOT NULL DEFAULT 'inbound', -- inbound|outbound|peer_outbound|peer_inbound
  system         TEXT NOT NULL,        -- "youtrack" | "sentry" | "federation"
  entity_type    TEXT NOT NULL,        -- bei federation: "skill"|"wiki_article"|"epic_share"|"task_update"
  entity_id      TEXT NOT NULL,
  payload        JSONB NOT NULL,
  attempts       INT NOT NULL DEFAULT 0,
  next_retry_at  TIMESTAMPTZ,
  state          TEXT NOT NULL DEFAULT 'pending', -- pending|processing|done|dead|cancelled|quarantined
  -- cancelled:    Eintrag wurde manuell abgebrochen (Admin-Aktion)
  -- quarantined:  Verdächtige Einträge nach Key-Kompromittierung (→ federation.md#key-kompromittierung--notfallprozedur)
  routing_state  TEXT DEFAULT 'unrouted',         -- unrouted|routed|ignored — für Triage-Anzeige
  -- unrouted: wartet auf manuelle Entscheidung in Triage Station
  -- routed:   wurde einem Epic zugewiesen (manuell oder auto-pgvector)
  -- ignored:  Admin hat bewusst entschieden, Event nicht zu routen; bleibt lesbar für Audit
  target_node_id UUID REFERENCES nodes(id), -- gesetzt bei direction='peer_outbound'
  created_at     TIMESTAMPTZ DEFAULT now()
);
```

> Vollständiges Schema: [data-model.md](../architecture/data-model.md)

### Retry-Strategie

```text
next_retry_at = now() + 2^attempts * 60s

Attempt 1: +1 min
Attempt 2: +2 min
Attempt 3: +4 min
Attempt 4: +8 min
Attempt 5: +16 min → Dead Letter Queue
```

Konfigurierbar via `HIVEMIND_DLQ_MAX_ATTEMPTS` (default: 5).

---

## Dead Letter Queue

Nach `attempts >= 5` wird der Eintrag in die `sync_dead_letter` verschoben (`direction = 'outbound'` **und** `'peer_outbound'` — identische Retry-Logik für externe Systeme und Peer-Nodes):

```sql
CREATE TABLE sync_dead_letter (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  outbox_id   UUID NOT NULL REFERENCES sync_outbox(id),
  system      TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id   TEXT NOT NULL,
  payload     JSONB NOT NULL,
  error       TEXT,
  failed_at   TIMESTAMPTZ DEFAULT now(),
  requeued_by UUID REFERENCES users(id),
  requeued_at TIMESTAMPTZ
);
```

- **Admin-Aktion (MCP):** `hivemind/requeue_dead_letter { "id": "uuid" }`
  - setzt den zugehörigen `sync_outbox`-Eintrag zurück auf `state='pending'`, `attempts=0`, `next_retry_at=now()`
  - schreibt `requeued_by` und `requeued_at` auf den Dead-Letter-Eintrag
- Optionaler REST-Alias: `POST /admin/dlq/{id}/requeue` kann intern denselben Service aufrufen
- **Kein Redis** in Phase 1–7; bei hohem Volumen in Phase 8 evaluieren

---

## Ingest-Flow (Webhooks)

```text
YouTrack/Sentry Event kommt über Webhook
  → Ingest prüft sync_outbox.dedup_key (z.B. "youtrack:event:1718036400:ISSUE-42") auf Existenz
  → Falls dedup_key bereits vorhanden: Event verwerfen (idempotent)
  → Sonst: Event mit direction='inbound' in sync_outbox eintragen
  → Hinweis: Folge-Updates derselben Issue sind erlaubt, solange dedup_key (Event-ID) neu ist
  → Routing per pgvector mit Confidence-Threshold (Phase 7+; Phase 3: alles [UNROUTED])
  → >= 0.85 Confidence: auto-assign zu Epic, state = incoming
  → < 0.85 Confidence: routing_state = 'unrouted', sichtbar in Triage Station
  → Phase 1-2: Kein Auto-Routing, alles manuell via Triage
```

> **dedup_key:** Pflichtfeld für alle Webhook-Events (`"system:event-id"` Format, provider-stabil und case-normalisiert). Für manuell erstellte `outbound`-Einträge (z.B. Assignee-Rücksync) kann `dedup_key` NULL sein — in diesem Fall kein Duplikat-Check.
> **NULL-Semantik in PostgreSQL:** Die `UNIQUE`-Constraint auf `dedup_key` erlaubt mehrere NULL-Werte (PostgreSQL-Standard: NULL ≠ NULL). Das ist bewusst — manuelle `outbound`-Einträge ohne `dedup_key` werden nicht dedupliziert. Nur Webhook-Events mit gesetztem `dedup_key` profitieren vom Idempotenz-Schutz.

### Webhook-Authentifizierung

| Provider | Mechanismus | Konfiguration |
| --- | --- | --- |
| YouTrack | HMAC-SHA256 Signature im Header (`X-Hub-Signature-256`) | `HIVEMIND_YOUTRACK_WEBHOOK_SECRET` |
| Sentry | DSN + Shared Secret im Header (`sentry-hook-signature`) | `HIVEMIND_SENTRY_WEBHOOK_SECRET` |

Das Backend validiert die Signature **vor** dem Eintragen in `sync_outbox`. Fehlende oder ungültige Signature → HTTP 401 (kein Eintrag in Outbox). Webhook-Secrets werden als Env-Var konfiguriert und nie in der DB gespeichert.

### Replay-Schutz (Inbound-Webhooks)

Zusätzlich zur Signatur-Validierung werden folgende Maßnahmen gegen Replay-Angriffe angewendet:

| Maßnahme | Detail |
| --- | --- |
| **Timestamp-Validierung** | Der Webhook muss einen Timestamp-Header mitliefern (`X-Webhook-Timestamp` bzw. provider-spezifisch). Events mit Timestamp > 5 Minuten in Vergangenheit oder Zukunft werden verworfen (HTTP 401). Toleranz konfigurierbar via `HIVEMIND_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS` (default: 300). |
| **Nonce / Event-ID Dedup** | Jeder Webhook-Event muss eine eindeutige Event-ID liefern (YouTrack: `X-Hub-Delivery`, Sentry: `sentry-hook-resource`). Diese ID fließt in den `dedup_key` der `sync_outbox`. Da `dedup_key` UNIQUE ist, wird ein replayed Event beim INSERT abgelehnt (idempotent, kein Fehler nach außen). **Nonce-TTL:** `dedup_key`-Einträge in `sync_outbox` mit `state='done'` dienen als Nonce-Speicher. Für Performance: Partial Index `CREATE INDEX idx_dedup_active ON sync_outbox(dedup_key) WHERE state != 'done'` beschleunigt den Duplikat-Check. Optional: `HIVEMIND_WEBHOOK_NONCE_TTL_DAYS` (Default: 30) — nach diesem Zeitraum werden `dedup_key`-Werte auf `done`-Einträgen auf NULL gesetzt (Speicher-Optimierung; Replay nach 30 Tagen theoretisch möglich aber durch Timestamp-Validierung abgefangen). |
| **HMAC über Timestamp** | Der Timestamp ist Teil des signierten Payloads: `HMAC(secret, timestamp + "." + body)`. Damit kann ein Angreifer den Timestamp nicht manipulieren ohne die Signatur zu invalide. |

> **Hinweis:** YouTrack und Sentry liefern jeweils eigene Event-IDs und Signatur-Mechanismen. Die Timestamp-Toleranz gilt einheitlich. Für Provider, die keinen eigenen Timestamp-Header senden, wird der Server-Empfangszeitpunkt verwendet (weniger sicher, aber akzeptabel mit HMAC + Dedup).

---

## Dispatch-Flow (Outbox-Consumer, Phase 7+)

```text
Hivemind erzeugt externes Update (z.B. Assignee-/Status-Änderung)
  → schreibt direction='outbound', state='pending' in sync_outbox
  → Outbox-Consumer verarbeitet nur direction='outbound' + state='pending'
  → Erfolg: state='done'
  → Fehler: attempts++ + next_retry_at setzen
  → Nach max attempts: Eintrag in sync_dead_letter
```

> **Polling-Intervall:** Der Outbox-Consumer pollt alle 30 Sekunden nach neuen `pending`-Einträgen (konfigurierbar via `HIVEMIND_OUTBOX_POLL_INTERVAL_SECONDS`, default: 30). Bei hohem Volumen in Phase 8: Evaluierung von `pg_notify`/LISTEN für Push-basierte Verarbeitung.

---

## pgvector Routing (Phase 7+)

1. Event empfangen (Webhook oder manueller Ingest)
2. Embedding erstellen: `title + description + (stack trace summary wenn Sentry)`
3. pgvector-Similarity vs. alle aktiven Epic-Embeddings
4. Confidence = Cosine-Similarity-Score des besten Treffers
5. `>= 0.85` → auto-assign zu Epic, Status `incoming`
6. `< 0.85` → Triage-Item `[UNROUTED]`

**Confidence-Schwellwert:** 0.85 (konfigurierbar via `HIVEMIND_ROUTING_THRESHOLD`); gegen KPI "Routing-Precision >= 85%" messen und iterativ tunen.

---

## Federation-Outbox (Phase F)

Peer-to-Peer-Nachrichten nutzen dieselbe `sync_outbox` mit `direction = 'peer_outbound'` und `system = 'federation'`. Der Outbox-Consumer verarbeitet beide Richtungen (`outbound` + `peer_outbound`) mit identischer Retry-Logik.

### Dispatch-Flow (Peer-Outbound)

```text
Skill wird als 'federated' markiert (federation_scope = 'federated')
  → Backend erzeugt pro bekanntem Peer einen sync_outbox-Eintrag:
      direction = 'peer_outbound'
      system = 'federation'
      entity_type = 'skill'
      entity_id = skill.id
      target_node_id = peer.id
      payload = { skill_spec, signature }
  → Outbox-Consumer sendet POST /federation/skill/publish an peer.node_url
  → Erfolg: state = 'done'
  → Peer offline: Retry mit Exponential Backoff → bei Fehler DLQ
```

### Ingest-Flow (Peer-Inbound)

```text
POST /federation/* empfangen
  → Signatur-Validierung via Ed25519 (sender public_key aus nodes-Tabelle)
  → Ungültige Signatur → HTTP 401, kein Eintrag
  → Gültig: sync_outbox-Eintrag direction='peer_inbound' (Audit-Trail)
  → Entität in lokale DB übernehmen (origin_node_id = sender node_id)
  → Sofortige Verarbeitung (kein Retry nötig für inbound)
```

### Federation-spezifische entity_types

| entity_type | Auslöser | Payload-Inhalt |
| --- | --- | --- |
| `skill` | Skill mit `federation_scope='federated'` gemergt | Vollständige Skill-Spec inkl. Content |
| `wiki_article` | Wiki-Artikel mit `federation_scope='federated'` gespeichert | Vollständiger Artikel |
| `epic_share` | Admin weist Task einem Peer-Node zu | Epic-Spec + zugewiesene Task-Specs |
| `task_update` | Task-State ändert sich auf einem Peer-Node | task_id, new_state, result, artifacts |
| `code_discovery` | Kartograph erkundet neuen Code-Node | code_node + edges + origin |
| `discovery_session` | Kartograph startet/beendet Exploration einer Area | area, node_name, type ('start'\|'end') |
| `skill_change_proposal` | Gaertner reicht Skill-Change-Proposal ein (`submit_skill_proposal`) | proposal_id, skill_id, diff, rationale, proposed_by |
| `peer_status` | Lokaler Ping-Cron erkennt Peer als `inactive` UND es gibt delegierte Tasks | peer_node_id, status='inactive', affected_task_ids |

> `peer_status`-Einträge werden **lokal** vom Ping-Cron generiert (kein Push vom offline Peer), `direction = 'peer_inbound'`, `routing_state = 'unrouted'` → erscheinen in Triage Station als `[PEER OFFLINE]`. Nur erzeugt wenn `tasks.assigned_node_id = offline_peer.id` mit nicht-terminalem State existiert.

---

## Wiki-Conflict-Resolution bei Federation

Wiki-Artikel können über Federation geteilt werden (`federation_scope='federated'`). Konflikte entstehen wenn zwei Peers denselben Artikel gleichzeitig bearbeiten.

### Konfliktregeln für Wiki

| Situation | Verhalten | Begründung |
| --- | --- | --- |
| Origin-Node editiert eigenen Artikel | Normaler Write | Origin-Authority gilt |
| Peer empfängt Update mit höherer `version` | Übernehmen (aktualisieren) | Höhere Version gewinnt |
| Peer empfängt Update mit gleicher `version` | **Last-Write-Wins** (Timestamp `updated_at` vergleichen) | Einfachste Strategie für Phase F; kein Merge-Aufwand |
| Peer empfängt Update mit niedrigerer `version` | Verwerfen (veraltet) | Lokale Version ist aktueller |
| Lokaler Edit auf empfangenem Artikel (Peer ist nicht Origin) | **Nicht erlaubt** — Read-only-Kopie | Origin-Authority: nur Origin-Node darf editieren |

**Hinweis:** Wiki-Artikel haben eine `origin_node_id`. Nur der Origin-Node kann den Artikel editieren. Empfangende Peers erhalten Read-only-Kopien. Änderungsvorschläge von Peers können als manuelles Feedback (z.B. über Decision Request oder Chat) an die Origin-Node kommuniziert werden. Es gibt keine automatischen Change-Proposals für Wiki-Artikel über Federation.

> **Zukunft:** Falls Multi-Origin-Editing gewünscht wird (zwei Peers bearbeiten denselben Artikel), muss ein CRDT- oder OT-basierter Merge implementiert werden. Das ist für Phase F nicht geplant.

→ Vollständige Federation-Spec: [federation.md](../features/federation.md)
