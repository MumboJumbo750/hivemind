# Hive Station — Federation Control Plane

← [Index](../../masterplan.md) | [Federation](./federation.md)

**Typ:** Eigenständiger, optionaler Microservice (nicht Teil des Hivemind-Hauptprozesses)
**Verfügbar ab:** Phase F (wenn `hub_assisted` oder `hub_relay` Topologie gewünscht)
**Voraussetzung:** Mindestens 2 Hivemind-Nodes mit abgeschlossener Phase 2

---

## Zweck

Die Hive Station ist ein **leichtgewichtiger Control-Plane-Server** für Hivemind-Federations. Sie löst drei Probleme, die `direct_mesh` mit statischer `peers.yaml` nicht abdeckt:

| Problem | Ohne Hive Station | Mit Hive Station |
| --- | --- | --- |
| **Neue Nodes** | Jeder Peer muss `peers.yaml` manuell aktualisieren | Node registriert sich einmalig; alle Peers sehen ihn automatisch |
| **Online-Status** | Erst beim nächsten `/federation/ping`-Timeout erkannt (bis zu 5 Min) | Heartbeat-basierte Presence mit Sekunden-Genauigkeit |
| **Instabile Netze** | Peer offline → Outbox-Retry → DLQ nach 5 Fehlversuchen | Relay puffert und stellt zu sobald Peer wieder erreichbar |

### Was die Hive Station NICHT ist

- **Keine Origin-Authority** — Entitäten (Epics, Tasks, Skills, Wiki) werden nie auf der Station gespeichert oder verwaltet
- **Kein Signing-Node** — Die Station hat kein Ed25519-Keypair und signiert keine Nachrichten
- **Kein Single Point of Failure** — Jeder Node arbeitet bei Station-Ausfall mit lokalem Peer-Cache weiter
- **Kein Pflicht-Bestandteil** — `direct_mesh` Topologie funktioniert vollständig ohne Station

---

## Architektur

```text
┌──────────────────────────────────────────────────────────────┐
│                      Hive Station                            │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │
│  │ Peer Registry │  │  Presence    │  │  Relay (optional)  │ │
│  │  (SQLite)     │  │  (in-memory) │  │  (store+forward)   │ │
│  └──────────────┘  └──────────────┘  └────────────────────┘ │
│                                                              │
│  Auth: Bearer Token (HIVE_STATION_AUTH_TOKEN)                │
│  Signing: keine — Payloads bleiben Node-signiert             │
└──────────────────────────────────────────────────────────────┘
         ▲              ▲              ▲
         │ register     │ heartbeat    │ relay
         │ GET peers    │              │ (opaque forward)
    ┌────┴───┐    ┌────┴───┐    ┌────┴───┐
    │ Alex   │    │  Ben   │    │ Clara  │
    │ (Node) │    │ (Node) │    │ (Node) │
    └────────┘    └────────┘    └────────┘
```

### Design-Prinzipien

1. **Opak für Payloads** — Die Station leitet Relay-Nachrichten unverändert weiter. Sie kann Payloads nicht entschlüsseln oder manipulieren (Ed25519-Signaturen bleiben End-to-End).
2. **Stateless Presence** — Online-Status lebt ausschließlich im Memory. Station-Neustart = alle Nodes gelten als `unknown` bis zum nächsten Heartbeat.
3. **Minimal Storage** — Nur die Peer-Registry ist persistent (SQLite). Kein pgvector, kein PostgreSQL, keine Embeddings.
4. **Token-basierte Auth** — Ein gemeinsamer Bearer Token für alle Nodes der Gilde. Kein JWT, kein RBAC.

---

## Stack & Deployment

| Komponente | Technologie |
| --- | --- |
| Runtime | Python 3.12 + FastAPI (uvicorn) |
| Storage | SQLite (Peer Registry, Relay Queue) |
| Presence | In-Memory Dict (TTL-basiert) |
| Container | Docker Image `hivemind-hive-station:latest` |
| Größe | < 500 LOC, < 50 MB Docker Image |

### Docker Compose (eigenständig)

```yaml
# hive-station/docker-compose.yml
services:
  hive-station:
    image: hivemind-hive-station:latest
    ports:
      - "9000:9000"
    environment:
      HIVE_STATION_AUTH_TOKEN: "${HIVE_STATION_AUTH_TOKEN}"
      HIVE_STATION_PORT: 9000
      HIVE_STATION_RELAY_ENABLED: "false"        # true für hub_relay
      HIVE_STATION_RELAY_MAX_PAYLOAD_KB: 512      # Max-Größe eines Relay-Payloads
      HIVE_STATION_RELAY_TTL_HOURS: 72            # Nicht-zustellbare Relay-Nachrichten verfallen
      HIVE_STATION_HEARTBEAT_TIMEOUT_SECONDS: 120 # Node gilt als offline nach N Sekunden ohne Heartbeat
      HIVE_STATION_DB_PATH: "/data/hive-station.db"
    volumes:
      - hive-station-data:/data

volumes:
  hive-station-data:
```

> **Deployment-Optionen:** Die Hive Station kann (a) auf einem dedizierten Server im VPN laufen, (b) als Sidecar auf einem der Hivemind-Nodes laufen, oder (c) auf einem öffentlich erreichbaren Server (z.B. für Teams ohne gemeinsames VPN — dann ist HTTPS Pflicht). Die Station hat **keinen Zugriff** auf Hivemind-Datenbanken.

---

## Konfiguration (Env-Variablen)

| Variable | Typ | Default | Beschreibung |
| --- | --- | --- | --- |
| `HIVE_STATION_AUTH_TOKEN` | TEXT | *Pflicht* | Shared Secret für alle Nodes der Gilde. Wird beim Setup generiert und an alle Nodes verteilt. |
| `HIVE_STATION_PORT` | INT | `9000` | HTTP-Port |
| `HIVE_STATION_RELAY_ENABLED` | BOOL | `false` | Store-and-Forward Relay aktivieren (`hub_relay`) |
| `HIVE_STATION_RELAY_MAX_PAYLOAD_KB` | INT | `512` | Maximale Payload-Größe für Relay-Nachrichten (KB) |
| `HIVE_STATION_RELAY_TTL_HOURS` | INT | `72` | TTL für gepufferte Relay-Nachrichten (Stunden) |
| `HIVE_STATION_HEARTBEAT_TIMEOUT_SECONDS` | INT | `120` | Timeout bis ein Node als `offline` gilt |
| `HIVE_STATION_DB_PATH` | TEXT | `./hive-station.db` | Pfad zur SQLite-Datenbank |
| `HIVE_STATION_LOG_LEVEL` | TEXT | `info` | `debug|info|warning|error` |
| `HIVE_STATION_CORS_ORIGINS` | TEXT | `*` | CORS-Origins (nur relevant wenn Station über Browser erreichbar) |

---

## Datenmodell (SQLite)

```sql
-- Registrierte Nodes (persistent)
CREATE TABLE peers (
  node_id     TEXT PRIMARY KEY,           -- UUID als Text
  node_name   TEXT NOT NULL,
  node_url    TEXT NOT NULL UNIQUE,
  public_key  TEXT NOT NULL,              -- Ed25519 Public Key (PEM)
  registered_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Relay-Queue (nur wenn HIVE_STATION_RELAY_ENABLED=true)
CREATE TABLE relay_queue (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  target_id   TEXT NOT NULL,              -- Ziel-Node-ID (FK logisch auf peers.node_id)
  sender_id   TEXT NOT NULL,              -- Absender-Node-ID
  payload     BLOB NOT NULL,              -- Opaker, signierter Payload (unverändert weiterleiten)
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at  TEXT NOT NULL,              -- created_at + RELAY_TTL_HOURS
  attempts    INTEGER NOT NULL DEFAULT 0, -- Zustellversuche
  state       TEXT NOT NULL DEFAULT 'pending' -- pending|delivered|expired
);

CREATE INDEX idx_relay_queue_target ON relay_queue(target_id, state);
CREATE INDEX idx_relay_queue_expires ON relay_queue(expires_at) WHERE state = 'pending';
```

> **Kein `presence`-Table** — Online-Status lebt im Memory als `dict[node_id, datetime]`. Bei Station-Neustart sind alle Nodes `unknown` bis zum nächsten Heartbeat (max 60 Sekunden).

---

## REST API

Alle Endpoints unter `/hive/`. Auth via `Authorization: Bearer <HIVE_STATION_AUTH_TOKEN>` Header — fehlt oder falsch → HTTP 401.

### Peer Registry

```text
POST   /hive/register
       Body: { "node_id": "uuid", "node_name": "alex-hivemind",
               "node_url": "http://192.168.1.10:8000",
               "public_key": "ed25519:pub:AbCdEfGh..." }
       → 201 { "registered": true, "peer_count": 3 }
       → 200 (wenn node_id bereits registriert — Update von node_name/node_url/public_key)
       → 401 (ungültiger Token)
       → 422 (Pflichtfelder fehlen oder node_url nicht erreichbar)
       Validierung:
         - node_id: valid UUID
         - node_url: gültiges HTTP(S)-URL-Format
         - public_key: beginnt mit "ed25519:pub:"
         - node_name: 1–64 Zeichen, alphanumerisch + Bindestrich

DELETE /hive/register/:node_id
       → 204 (Node entfernt + alle Relay-Queue-Einträge für diesen Node gelöscht)
       → 404 (Node nicht bekannt)
       → 401 (ungültiger Token)
       Hinweis: Ein Node kann sich selbst de-registrieren (Offboarding).
       Andere Nodes können fremde Nodes NICHT de-registrieren — nur der
       Station-Betreiber kann das via direkten DB-Zugriff oder Admin-Token.
```

### Presence (Heartbeat)

```text
POST   /hive/heartbeat
       Body: { "node_id": "uuid" }
       → 200 { "online_peers": 2, "offline_peers": 1 }
       → 401 (ungültiger Token)
       → 404 (node_id nicht registriert — Node muss sich erst registrieren)
       Seiteneffekt: Aktualisiert last_seen Timestamp im Memory.
       Empfohlenes Intervall: 60 Sekunden (konfiguriert auf Node-Seite via
       HIVEMIND_FEDERATION_PING_INTERVAL).
```

### Peer Discovery

```text
GET    /hive/peers
       → 200 {
           "peers": [
             {
               "node_id": "uuid",
               "node_name": "alex-hivemind",
               "node_url": "http://192.168.1.10:8000",
               "public_key": "ed25519:pub:AbCdEfGh...",
               "online": true,
               "last_seen": "2026-03-10T14:32:00Z"
             },
             ...
           ],
           "total": 3,
           "online": 2
         }
       → 401 (ungültiger Token)
       Online-Logik: last_seen < HEARTBEAT_TIMEOUT_SECONDS → online=true
       Sortierung: online zuerst, dann nach node_name alphabetisch.

GET    /hive/peers/:node_id
       → 200 { "node_id": "...", "node_name": "...", ... }
       → 404 (unbekannter Node)
       → 401 (ungültiger Token)
```

### Relay (nur wenn `HIVE_STATION_RELAY_ENABLED=true`)

```text
POST   /hive/relay/:target_node_id
       Body: <opaker signierter Payload> (Content-Type: application/octet-stream)
       Header: X-Hivemind-Sender: <sender_node_id>
       → 202 { "queued": true, "queue_id": 42 }
       → 401 (ungültiger Token)
       → 404 (target_node_id nicht registriert)
       → 413 (Payload > RELAY_MAX_PAYLOAD_KB)
       → 503 (Relay nicht aktiviert)
       Seiteneffekt: Payload wird in relay_queue gespeichert.
       Die Station leitet NICHT sofort weiter — der Empfänger-Node
       holt seine Nachrichten ab (Pull-Modell, siehe unten).

GET    /hive/relay/inbox
       Header: X-Hivemind-Node: <own_node_id>
       → 200 {
           "messages": [
             { "id": 42, "sender_id": "uuid", "payload": "<base64>",
               "created_at": "2026-03-10T14:32:00Z" },
             ...
           ],
           "remaining": 0
         }
       → 401 (ungültiger Token)
       → Limit: 50 Nachrichten pro Abruf (älteste zuerst)
       → Nur Nachrichten für den anfragenden Node (target_id = own_node_id)

POST   /hive/relay/ack
       Body: { "node_id": "uuid", "message_ids": [42, 43, 44] }
       → 200 { "acknowledged": 3 }
       → 401 (ungültiger Token)
       Seiteneffekt: relay_queue.state → 'delivered' für diese IDs.
       Nur der target_node darf seine eigenen Nachrichten acknowledgen.
```

### Health

```text
GET    /hive/health
       → 200 { "status": "ok", "peers_registered": 3,
               "peers_online": 2, "relay_enabled": false,
               "relay_queue_pending": 0, "uptime_seconds": 86400 }
       → Kein Auth nötig (öffentlich für Monitoring).
```

---

## Relay-Zustellungsprotokoll

Der Relay-Mechanismus folgt einem **Pull-Modell** um NAT-/Firewall-Probleme zu umgehen:

```text
Sender (Alex)                    Hive Station                   Empfänger (Ben)
     │                                │                                │
     │ POST /hive/relay/ben-id        │                                │
     │ [signierter Payload] ─────────→│ relay_queue INSERT             │
     │                         202    │                                │
     │←──────────────────────────────│                                │
     │                                │                                │
     │                                │   GET /hive/relay/inbox        │
     │                                │←──────────────────────────────│
     │                                │  200 [messages] ──────────────→│
     │                                │                                │ Signatur prüfen
     │                                │   POST /hive/relay/ack        │ Payload verarbeiten
     │                                │←──────────────────────────────│
     │                                │  state → 'delivered'           │
```

### Relay-Zustellungs-Cron (auf der Station)

Die Station hat **keinen** Push-Mechanismus. Stattdessen bereinigt ein interner Cron-Job abgelaufene Nachrichten:

```text
Alle 60 Minuten:
  DELETE FROM relay_queue
  WHERE state = 'pending' AND expires_at < datetime('now')
  → Abgelaufene Nachrichten (nach RELAY_TTL_HOURS) werden entfernt
  → Logging: "Expired N relay messages for nodes: [...]"
```

### Relay-Polling auf Node-Seite

Hivemind-Nodes im `hub_relay`-Modus pollen die Station regelmäßig:

```text
Intervall: HIVEMIND_RELAY_POLL_INTERVAL_SECONDS (Default: 30)
Flow:
  1. GET /hive/relay/inbox (mit eigenem node_id)
  2. Für jede Nachricht:
     a) Ed25519-Signatur gegen sender's public_key prüfen
     b) Ungültig → loggen + ignorieren (NICHT acknowledgen → bleibt in Queue, wird nach TTL gelöscht)
     c) Gültig → an lokalen Federation-Handler weiterleiten (wie normaler POST /federation/*)
  3. POST /hive/relay/ack mit allen erfolgreich verarbeiteten message_ids
```

---

## Sicherheitsmodell

### Auth-Schichten

| Schicht | Mechanismus | Zweck |
| --- | --- | --- |
| **Station ↔ Node** | Bearer Token (`HIVE_STATION_AUTH_TOKEN`) | Stellt sicher dass nur Gilde-Mitglieder die Station nutzen |
| **Node ↔ Node** (via Relay) | Ed25519-Signatur im Payload | End-to-End-Integrität — Station kann Payloads nicht manipulieren |

### Angriffsvektoren & Mitigations

| Vektor | Risiko | Mitigation |
| --- | --- | --- |
| **Token-Leak** | Angreifer kann Fake-Nodes registrieren | Token rotate: neues Token setzen, alle Nodes aktualisieren. Fake-Node kann keine gültigen Ed25519-Signaturen senden → Payloads werden von Empfänger-Nodes abgelehnt. |
| **Station kompromittiert** | Falsche Peer-Discovery-Daten möglich (z.B. falsche `node_url`) | Empfänger-Nodes validieren immer Ed25519-Signatur. Falsche URLs führen zu Connection-Timeout, nicht zu Daten-Kompromittierung. Public Keys müssen initial manuell bestätigt werden (`pending_confirmation` in Node-UI). |
| **Relay Payload Manipulation** | Station könnte Relay-Payloads verändern | Payloads sind Ed25519-signiert. Manipulierte Payloads werden vom Empfänger mit 401 abgelehnt. |
| **Relay Flooding** | Angreifer flutet Relay-Queue | Max Payload Size (`RELAY_MAX_PAYLOAD_KB`), TTL-basierte Expiration, Rate Limit (s.u.) |
| **DoS auf Station** | Station nicht erreichbar | Alle Nodes fallen auf lokalen Peer-Cache + `peers.yaml` zurück. Kein Datenverlust, nur verzögerte Discovery. |

### Rate Limiting

| Endpoint-Kategorie | Limit | Zeitfenster |
| --- | --- | --- |
| `/hive/register` | 10 Requests | 60 Sekunden (pro IP) |
| `/hive/heartbeat` | 120 Requests | 60 Sekunden (pro IP) |
| `/hive/peers` | 60 Requests | 60 Sekunden (pro IP) |
| `/hive/relay/*` | 60 Requests | 60 Sekunden (pro IP) |
| `/hive/health` | Kein Limit | — |

### Token-Rotation

```text
1. Station-Betreiber setzt neues HIVE_STATION_AUTH_TOKEN
2. Station neu starten (Docker Compose restart)
3. Alle Nodes erhalten neues Token via HIVEMIND_HIVE_STATION_TOKEN Env-Var
4. Nodes neu starten oder Settings-Update (je nach Implementierung)
Downtime: Minimal — während der Rotation schlagen Station-Calls fehl,
Nodes arbeiten mit lokalem Cache weiter.
```

---

## Monitoring & Observability

### Health-Check

`GET /hive/health` (ohne Auth) liefert:

```json
{
  "status": "ok",
  "peers_registered": 3,
  "peers_online": 2,
  "relay_enabled": true,
  "relay_queue_pending": 5,
  "relay_queue_expired_24h": 2,
  "uptime_seconds": 86400,
  "version": "0.1.0"
}
```

### Logging

Strukturiertes JSON-Logging (stdout) — kompatibel mit Docker Log Drivers:

```json
{"level": "info", "event": "peer_registered", "node_id": "uuid", "node_name": "alex-hivemind", "timestamp": "..."}
{"level": "info", "event": "heartbeat", "node_id": "uuid", "timestamp": "..."}
{"level": "warning", "event": "peer_offline", "node_id": "uuid", "last_seen": "...", "timestamp": "..."}
{"level": "info", "event": "relay_queued", "sender_id": "uuid", "target_id": "uuid", "payload_kb": 12, "timestamp": "..."}
{"level": "info", "event": "relay_delivered", "target_id": "uuid", "message_count": 3, "timestamp": "..."}
{"level": "warning", "event": "relay_expired", "target_id": "uuid", "expired_count": 2, "timestamp": "..."}
```

### Metriken (optional, Phase 8+)

Wenn Prometheus-kompatibles Monitoring gewünscht, kann ein `/hive/metrics`-Endpoint aktiviert werden (`HIVE_STATION_METRICS_ENABLED=true`):

```text
hive_station_peers_registered    gauge    Anzahl registrierter Nodes
hive_station_peers_online        gauge    Anzahl aktuell online Nodes
hive_station_relay_queue_pending gauge    Anzahl wartender Relay-Nachrichten
hive_station_relay_delivered_total counter Gesamt zugestellte Relay-Nachrichten
hive_station_relay_expired_total  counter Gesamt abgelaufene Relay-Nachrichten
hive_station_requests_total       counter Requests pro Endpoint (Label: path, status)
```

---

## Client-Integration (Hivemind-Node-Seite)

### Relevante Env-Variablen (auf dem Hivemind-Node)

```text
HIVEMIND_FEDERATION_TOPOLOGY=hub_assisted    # oder hub_relay
HIVEMIND_HIVE_STATION_URL=http://station.vpn:9000
HIVEMIND_HIVE_STATION_TOKEN=<shared-secret>
HIVEMIND_RELAY_POLL_INTERVAL_SECONDS=30      # nur für hub_relay
```

### Node-Verhalten nach Topologie

| Topologie | Register | Heartbeat | Peer-Liste | Relay |
| --- | --- | --- | --- | --- |
| `direct_mesh` | — | — | `peers.yaml` + mDNS | — |
| `hub_assisted` | Beim Start + bei Änderungen | Alle 60s | `GET /hive/peers` beim Start + alle 5 Min | — |
| `hub_relay` | Wie `hub_assisted` | Wie `hub_assisted` | Wie `hub_assisted` | Poll-Inbox alle 30s + Outbox fallback auf Relay |

### Outbox-Fallback bei `hub_relay`

```text
Outbox-Consumer versucht direkte Zustellung:
  POST federation/skill/publish an peer.node_url
    → Erfolg: state='done' (wie bei direct_mesh)
    → Fehler (Timeout/Connection refused):
        1. Versuch via Relay: POST /hive/relay/:peer_id
        2. Relay-Erfolg (202): state='done' (Zustellung an Station bestätigt)
        3. Relay-Fehler: Normales Retry (Exponential Backoff → DLQ nach 5 Versuchen)
```

### Peer-Cache-Merge

Wenn ein Node sowohl `peers.yaml` als auch Hive Station nutzt (`hub_assisted`), werden beide Quellen gemergt:

```text
Priorität:
  1. peers.yaml (lokale Konfiguration hat Vorrang — Admin-Intent)
  2. Hive Station GET /hive/peers (ergänzt unbekannte Peers)
  3. mDNS (wenn aktiviert, niedrigste Priorität, immer pending_confirmation)

Konflikte:
  - Selbe node_id in peers.yaml + Station → peers.yaml gewinnt (URL, public_key)
  - Node in peers.yaml aber nicht auf Station → Bleibt lokal bekannt
  - Node auf Station aber nicht in peers.yaml → Wird hinzugefügt (status=active)
```

---

## Betriebsszenarien

### Szenario 1: Station-Ausfall

```text
Station nicht erreichbar (Netzwerk, Crash, Wartung):
  → Nodes erkennen Ausfall bei nächstem /hive/peers oder /hive/heartbeat Call
  → Logging: "WARN: Hive Station unreachable — using local peer cache"
  → Alle Discovery-Operationen nutzen lokalen peers-Cache (nodes-Tabelle)
  → Alle Federation-Operationen (Skill-Publish, Epic-Share) laufen weiter (direkte Zustellung)
  → Nur neue Peer-Registrierungen sind blockiert bis Station zurück
  → Bei hub_relay: Relay-Fallback nicht verfügbar → direkte Zustellung oder DLQ
  → Station wieder erreichbar → automatische Re-Registrierung + Peer-Cache-Refresh
```

### Szenario 2: Node-Migration (IP-Wechsel)

```text
Node wechselt VPN-IP (z.B. 192.168.1.10 → 192.168.1.20):
  1. Node aktualisiert HIVEMIND_NODE_URL in eigener Konfiguration
  2. Node sendet POST /hive/register mit neuer node_url (node_id bleibt gleich)
  3. Station aktualisiert peers.node_url
  4. Nächster GET /hive/peers von anderen Nodes liefert neue URL
  5. Andere Nodes aktualisieren lokalen Peer-Cache automatisch
```

### Szenario 3: Node-Offboarding

```text
Entwickler verlässt das Team:
  1. Admin auf dem scheidenden Node: hivemind federation leave
     → DELETE /hive/register/:own_node_id (De-Registrierung)
     → POST /federation/ping mit status='removed' an alle bekannten Peers
  2. Peers aktualisieren nodes.status = 'removed'
  3. Verwaiste Entitäten (Skills, Wiki mit origin_node_id = entfernter Node):
     → Bleiben lesbar (Soft-Delete: deleted_at gesetzt)
     → Können innerhalb 30 Tagen wiederhergestellt werden
  4. Falls Node nicht kooperiert (kein `leave`):
     → Jeder Peer: hivemind federation revoke-key --peer <node_id>
     → Station-Admin: DELETE /hive/register/:node_id (via direkten DB-Zugriff oder API)
```

---

## Upgrade-Pfad

| Von | Nach | Aufwand |
| --- | --- | --- |
| `direct_mesh` → `hub_assisted` | Station deployen, Nodes `TOPOLOGY=hub_assisted` setzen, `HIVE_STATION_URL` + Token konfigurieren. Nodes registrieren sich automatisch. `peers.yaml` bleibt als Fallback aktiv. | Minimal |
| `hub_assisted` → `hub_relay` | Station: `RELAY_ENABLED=true` setzen. Nodes: `TOPOLOGY=hub_relay` + `RELAY_POLL_INTERVAL` konfigurieren. | Minimal |
| `hub_relay` → `hub_assisted` | Nodes: `TOPOLOGY=hub_assisted`. Relay-Queue wird nicht mehr befüllt; bestehende Einträge verfallen nach TTL. | Minimal |
| `hub_assisted` → `direct_mesh` | Nodes: `TOPOLOGY=direct_mesh`, `HIVE_STATION_URL` leer. `peers.yaml` muss aktuell sein. Station kann heruntergefahren werden. | Manuell (`peers.yaml` pflegen) |

---

## Nicht im Scope

Die folgenden Features sind **bewusst nicht** Teil der Hive Station v1 und werden bei Bedarf nach Phase 8 evaluiert:

| Feature | Begründung |
| --- | --- |
| **Multi-Gilde-Support** | v1 kennt nur einen Token = eine Gilde. Mehrere Gilden erfordern Namespace-Isolation. |
| **Web-Dashboard** | Monitoring via `/hive/health` und Logs. Ein UI ist für einen reinen Control-Plane-Dienst Overkill. |
| **Persistente Presence** | Online-Status soll flüchtig sein. Historische Presence-Daten sind kein Requirement. |
| **TLS-Terminierung** | Die Station spricht HTTP. TLS wird vom Reverse Proxy (nginx, Caddy, Traefik) übernommen — wie bei den Hivemind-Nodes selbst. |
| **Automatische Key-Verteilung** | Public Keys werden von Nodes selbst verwaltet. Die Station speichert Keys nur für Discovery, nicht für Trust-Entscheidungen. |

---

## Zusammenfassung

```text
                    ┌─────────────────────────────────┐
                    │         Hive Station             │
                    │                                   │
                    │  Peer Registry  (SQLite)          │
                    │  Presence       (In-Memory)       │
                    │  Relay Queue    (SQLite, opt-in)  │
                    │                                   │
                    │  Auth: Bearer Token               │
                    │  Signing: KEINE                   │
                    │  Origin-Authority: KEINE           │
                    │  Pflicht: NEIN (direct_mesh OK)    │
                    └─────────────────────────────────┘
```

| Eigenschaft | Wert |
| --- | --- |
| **Typ** | Eigenständiger Microservice |
| **Stack** | Python + FastAPI + SQLite |
| **Größe** | < 500 LOC |
| **Docker** | `hivemind-hive-station:latest` |
| **Port** | 9000 (Default) |
| **Auth** | Shared Bearer Token |
| **Persistence** | SQLite (Peer Registry + Relay Queue) |
| **Pflicht** | Nein — nur für `hub_assisted` und `hub_relay` |
| **Datenhoheit** | Keine — reiner Control Plane |
