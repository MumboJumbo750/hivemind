# Phase F — Federation

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Jeder Entwickler betreibt seine eigene Hivemind-Instanz. Nodes im selben VPN können Skills, Wiki-Artikel und Epics teilen und Sub-Tasks gegenseitig delegieren.

**Voraussetzung:** Phase 2 abgeschlossen.
**Rollout-Hinweis:** Teams mit zentraler Instanz können Federation später aktivieren. Das Zielbild bleibt Federation-kompatibel (`direct_mesh` zuerst, `hub_assisted` optional danach).
**AI-Integration:** Keine — alles läuft manuell über Prompt Station (wie Phase 2).
**MCP-Tool-Hinweis:** Phase F implementiert Federation als REST-API-Endpoints (`/federation/*`). Die MCP-Tool-Wrapper (`hivemind/fork_federated_skill`, `start_discovery_session`, `end_discovery_session`) werden erst verfügbar wenn Phase 3 den MCP-Server bereitstellt. Vor Phase 3 sind alle Federation-Aktionen über die UI erreichbar (Buttons in Gilde-View, Settings, Command Deck).

---

## Deliverables

### Backend

- [ ] `node_identity`-Bootstrap: Beim ersten Start UUID + Ed25519-Keypair generieren, in `node_identity` speichern
- [ ] Federation Protocol API: `/federation/ping`, `/federation/skill/publish`, `/federation/wiki/publish`, `/federation/epic/share`, `/federation/task/update`, `/federation/sync`
- [ ] Signatur-Middleware: Alle `/federation/*` Requests via Ed25519 validieren (Public Key aus `nodes`-Tabelle)
- [ ] Outbox-Consumer für `peer_outbound`: `direction='peer_outbound'` verarbeiten (HTTP POST an `nodes.node_url`) — erster Outbox-Consumer überhaupt; der `outbound`-Consumer für YouTrack/Sentry folgt erst in Phase 7
- [ ] Skill/Wiki Publish-Trigger: Bei `lifecycle='active'` + `federation_scope='federated'` → Outbox-Einträge für alle bekannten Peers
- [ ] REST-Endpoint `POST /skills/fork` + MCP-Tool-Wrapper `hivemind/fork_federated_skill` (MCP-Wrapper erst ab Phase 3 nutzbar): federierten Skill lokal als Draft forken (`extends` auf Origin-Skill)
- [ ] Epic-Share-Flow: `assigned_node_id` auf Task setzen → Epic-Spec + Task-Spec an Peer-Node senden
- [ ] Task-Update-Empfang: Eingehende Task-State-Updates von Peer-Nodes verarbeiten + lokal spiegeln
- [ ] Heartbeat-Service: Regelmäßiger Ping an alle bekannten Peers (aktualisiert `nodes.last_seen`)
- [ ] `peers.yaml`-Loader: Beim Start Peer-Konfiguration in `nodes`-Tabelle einlesen
- [ ] Topologie-Schalter: `HIVEMIND_FEDERATION_TOPOLOGY` (`direct_mesh|hub_assisted|hub_relay`) unterstützt
- [ ] Optionaler Hive-Station-Client (`hub_assisted`): Register + Presence + Peer-Liste laden
- [ ] Fallback-Logik: Wenn Hive Station nicht erreichbar, mit lokalem Peer-Cache (`nodes`) + `peers.yaml` weiterarbeiten
- [ ] Optionaler Relay-Pfad (`hub_relay`): Outbox kann bei Bedarf über Hive Station store-and-forward zustellen

### Frontend

- [ ] Settings Tab: FEDERATION (Peer-Liste, eigene Node-ID/URL/Key, Peer hinzufügen/entfernen/blockieren)
- [ ] Settings Tab: Topologie-Auswahl (Direct Mesh / Hub-Assisted / Hub Relay)
- [ ] Settings Tab: Hive Station Felder (URL, Token) + Verbindungsstatus
- [ ] Shared Epic Dashboard: Task-Badges für Peer-zugewiesene Tasks (`[◈ ben-hivemind]`)
- [ ] Gilde-View: Federated-Skills-Sektion mit Read-only-Badge `[von: node-name]` + `[ÜBERNEHMEN]`-Button; die Integration in das Skill Lab (Arsenal) folgt in Phase 4 sobald Skill Lab gebaut ist
- [ ] `[ÜBERNEHMEN]` ruft `hivemind/fork_federated_skill` auf und erstellt lokalen Draft-Fork
- [ ] Node-Filter im Command Deck: Tasks nach Node filtern

---

## Technische Details

### Peer-Konfiguration (`peers.yaml`)

```yaml
peers:
  - name: ben-hivemind
    url: http://192.168.1.11:8000
    public_key: "ed25519:pub:..."
  - name: clara-hivemind
    url: http://192.168.1.12:8000
    public_key: "ed25519:pub:..."
```

### Federation-Env-Variablen

```text
HIVEMIND_FEDERATION_ENABLED=true
HIVEMIND_FEDERATION_TOPOLOGY=direct_mesh
HIVEMIND_NODE_NAME=alex-hivemind
HIVEMIND_KEY_PASSPHRASE=<sicheres-passwort>
HIVEMIND_PEERS_CONFIG=./peers.yaml
HIVEMIND_HIVE_STATION_URL=
HIVEMIND_HIVE_STATION_TOKEN=
HIVEMIND_HIVE_RELAY_ENABLED=false
```

### Topologie-Modi

| Modus | Discovery | Transport |
| --- | --- | --- |
| `direct_mesh` | `peers.yaml` (+ optional mDNS) | direkt Node -> Node |
| `hub_assisted` | Hive Station + lokaler Peer-Cache | direkt Node -> Node |
| `hub_relay` | Hive Station + lokaler Peer-Cache | direkt bevorzugt, optional via Relay |

**Wichtig:** Hive Station ist nur Control Plane (Discovery/Presence/Relay), nicht Origin-Authority für Epics/Tasks/Skills/Wiki.

### docker-compose.yml — keine Änderung nötig

Federation läuft im selben FastAPI-Prozess wie das Haupt-Backend. Keine neuen Services.

---

## Acceptance Criteria

- [ ] Node-Identität wird beim ersten Start automatisch generiert (`node_identity` enthält genau 1 Zeile)
- [ ] `POST /federation/ping` antwortet mit `{ node_id, node_name, public_key }`
- [ ] Ungültige Ed25519-Signatur → HTTP 401
- [ ] Skill mit `federation_scope='federated'` → Outbox-Einträge pro Peer nach Merge
- [ ] Peer-Node empfängt Skill + speichert mit `origin_node_id` gesetzt
- [ ] Peer-Node kann federierten Skill nicht editieren (HTTP 403)
- [ ] `hivemind/fork_federated_skill` erstellt aus federiertem Skill einen lokalen Draft-Fork mit `extends`-Link
- [ ] Epic mit Peer-zugewiesenem Task → Task erscheint in Peer-Prompt-Station
- [ ] Task-State-Update von Peer → State auf Origin-Node korrekt gespiegelt
- [ ] Peer offline → Outbox-Retry greift; bei 5 Fehlern → DLQ
- [ ] Settings FEDERATION Tab zeigt alle bekannten Peers mit Status
- [ ] `direct_mesh`: Node-Discovery aus `peers.yaml` funktioniert ohne Hive Station
- [ ] `hub_assisted`: Node registriert sich bei Hive Station und erhält Peer-Liste/Presence
- [ ] Hive Station temporär offline: Node arbeitet mit lokalem Peer-Cache weiter
- [ ] `hub_relay` (wenn aktiviert): Peer-Update kann über Relay zugestellt werden und bleibt signaturgeprüft

---

## Abhängigkeiten

- Phase 2 abgeschlossen (Auth, Node-Keypair-Bootstrap)

## Öffnet folgende Phase

→ [Phase 3: MCP Read-Tools](./phase-3.md)
