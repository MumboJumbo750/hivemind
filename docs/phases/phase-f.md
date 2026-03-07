# Phase F — Federation

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Jeder Entwickler betreibt seine eigene Hivemind-Instanz. Nodes im selben VPN können Skills, Wiki-Artikel und Epics teilen und Sub-Tasks gegenseitig delegieren.

**Voraussetzung:** Phase 2 abgeschlossen.
**Rollout-Hinweis:** Teams mit zentraler Instanz können Federation später aktivieren. Das Zielbild bleibt Federation-kompatibel (`direct_mesh` zuerst, `hub_assisted` optional danach).
**AI-Integration:** Keine — alles läuft manuell über Prompt Station (wie Phase 2).
**MCP-Tool-Hinweis:** Phase F implementiert Federation als REST-API-Endpoints (`/federation/*`). Die MCP-Tool-Wrapper (`hivemind-fork_federated_skill`, `hivemind-start_discovery_session`, `hivemind-end_discovery_session`) werden erst verfügbar wenn Phase 3 den MCP-Server bereitstellt. Vor Phase 3 sind alle Federation-Aktionen über die UI erreichbar (Buttons in Gilde-View, Settings, Command Deck).

## Phasen-Sequenz & Mercenary Loadout

Phase F läuft **nach Phase 2** und **vor Phase 3**. Die Sequenz ist linear: `1 → 2 → F → 3 → 4 → 5 → ...`

**Was Phase F liefert (keine Phase-4-Abhängigkeit):**

- Gilde-View mit Federated Skills (Read-only-Anzeige + `[ÜBERNEHMEN]`-Button)
- Basis-Loadout-Anzeige in der Prompt Station (zeigt gepinnte Skills inkl. federated, Token-Counts, Guards)
- Epic-Share-Flow + Task-Delegation an Peers
- Peer-Discovery, Heartbeat, Outbox-Consumer

**Was erst in Phase 4 dazukommt (Skill Lab):**

- Vollständige Skill-Lab-UI (Arsenal-View) mit Edit, Merge, Draft-Management
- Integration federated Skills **ins Skill Lab** (Bearbeitung, Fork-Workflow im Skill Lab)
- `[ÜBERNEHMEN]`-Button in Phase F erstellt einen lokalen Draft-Fork, aber das Skill Lab zur Verwaltung dieses Drafts folgt erst in Phase 4

**Konkretes Beispiel:**

```text
Phase F (nach Phase 2):
  ✓ Ben sieht Alex's federierten Skill "FastAPI Auth" in der Gilde-View
  ✓ Ben klickt [ÜBERNEHMEN] → erstellt lokalen Draft (in DB, noch kein UI zur Bearbeitung)
  ✓ Prompt Station zeigt das Loadout mit federated Skills korrekt an
  ✗ Ben kann den Draft noch nicht im Skill Lab bearbeiten (Skill Lab nicht vorhanden)

Phase 4 (nach Phase F):
  ✓ Skill Lab ist vollständig — Ben öffnet seinen Draft und bearbeitet ihn
  ✓ Federated Skills erscheinen im Arsenal neben lokalen Skills
```

> **Kein Chicken-and-Egg-Problem:** Phase F baut den Federation-Transport und die Datenstrukturen. Phase 4 baut die UI-Schicht für Skill-Management. Beides ist unabhängig implementierbar.

---

## Deliverables

### Backend

- [ ] `node_identity`-Bootstrap: Beim ersten Start UUID + Ed25519-Keypair generieren, in `node_identity` speichern
- [ ] Federation Protocol API: `/federation/ping`, `/federation/skill/publish`, `/federation/wiki/publish`, `/federation/epic/share`, `/federation/task/update`, `/federation/sync`
- [ ] Signatur-Middleware: Alle `/federation/*` Requests via Ed25519 validieren (Public Key aus `nodes`-Tabelle)
- [ ] Outbox-Consumer für `peer_outbound`: `direction='peer_outbound'` verarbeiten (HTTP POST an `nodes.node_url`) — erster Outbox-Consumer überhaupt; der `outbound`-Consumer für YouTrack/Sentry folgt erst in Phase 7
- [ ] Skill/Wiki Publish-Trigger: Bei `lifecycle='active'` + `federation_scope='federated'` → Outbox-Einträge für alle bekannten Peers
- [ ] REST-Endpoint `POST /skills/fork` + MCP-Tool-Wrapper `hivemind-fork_federated_skill` (MCP-Wrapper erst ab Phase 3 nutzbar): federierten Skill lokal als Draft forken (`extends` auf Origin-Skill)
- [ ] Epic-Share-Flow: `assigned_node_id` auf Task setzen → Epic-Spec + Task-Spec an Peer-Node senden
- [ ] Task-Update-Empfang: Eingehende Task-State-Updates von Peer-Nodes verarbeiten + lokal spiegeln
- [ ] Heartbeat-Service: Regelmäßiger Ping an alle bekannten Peers (aktualisiert `nodes.last_seen`)
- [ ] **Federation-Notification-Types** (vor Phase 6: client-calculated aus SSE-Events; ab Phase 6: Notification-Service-Einträge):
  - `task_delegated` — bei `assigned_node_id` setzen → Epic-Owner
  - `peer_task_done` — bei eingehendem Task-Update mit `state='done'` von Peer → Epic-Owner
  - `peer_online` — wenn `nodes.status` von `inactive` → `active` wechselt → alle User
  - `peer_offline` — wenn Peer mit delegierten Tasks als `inactive` erkannt wird → alle Admins
  - `federated_skill` — bei Empfang eines neuen federierten Skills → alle User
  - `discovery_session` — bei `start_discovery_session` / `end_discovery_session` eines Peers → alle User
  > **Hinweis:** Der backend-seitige Notification-Service wird erst in Phase 6 implementiert. Bis dahin werden diese Notification-Types **client-calculated** aus den entsprechenden SSE-Events (Federation-State-Changes) abgeleitet — analog zum Phase-2-Muster für andere Notifications.
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
- [ ] `[ÜBERNEHMEN]` ruft `hivemind-fork_federated_skill` auf und erstellt lokalen Draft-Fork
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

### docker-compose.yml — keine Änderung am Haupt-File nötig

Federation läuft im selben FastAPI-Prozess wie das Haupt-Backend. Keine neuen Services nötig — die Federation-Env-Variablen (siehe oben) werden direkt in `docker-compose.yml` oder via `.env`-Datei konfiguriert.

**Empfohlenes Muster für Federation-spezifische Konfiguration:** Ein separates `docker-compose.override.yml` hält Federation-Variablen getrennt vom Basis-Stack und kann versioniert oder ausgeblendet werden:

```yaml
# docker-compose.override.yml — nur auf Federation-Nodes einspielen
services:
  backend:
    environment:
      HIVEMIND_FEDERATION_ENABLED: "true"
      HIVEMIND_FEDERATION_TOPOLOGY: "direct_mesh"
      HIVEMIND_NODE_NAME: "alex-hivemind"
      HIVEMIND_KEY_PASSPHRASE: "${HIVEMIND_KEY_PASSPHRASE}"  # aus .env
      HIVEMIND_PEERS_CONFIG: "/app/peers.yaml"
      HIVEMIND_FEDERATION_PING_INTERVAL: "60"
      HIVEMIND_FEDERATION_OFFLINE_THRESHOLD: "3"
    volumes:
      - ./peers.yaml:/app/peers.yaml:ro
```

> Docker Compose lädt `docker-compose.override.yml` automatisch wenn es neben `docker-compose.yml` liegt (`docker compose up` ohne `-f`-Flag). Nodes ohne Federation lassen das Override-File einfach weg — kein Deployment-Unterschied am Haupt-Stack.

---

## Acceptance Criteria

- [ ] Node-Identität wird beim ersten Start automatisch generiert (`node_identity` enthält genau 1 Zeile)
- [ ] `POST /federation/ping` antwortet mit `{ node_id, node_name, public_key }`
- [ ] Ungültige Ed25519-Signatur → HTTP 401
- [ ] Skill mit `federation_scope='federated'` → Outbox-Einträge pro Peer nach Merge
- [ ] Peer-Node empfängt Skill + speichert mit `origin_node_id` gesetzt
- [ ] Peer-Node kann federierten Skill nicht editieren (HTTP 403)
- [ ] `hivemind-fork_federated_skill` erstellt aus federiertem Skill einen lokalen Draft-Fork mit `extends`-Link
- [ ] Epic mit Peer-zugewiesenem Task → Task erscheint in Peer-Prompt-Station
- [ ] Task-State-Update von Peer → State auf Origin-Node korrekt gespiegelt
- [ ] Peer offline → Outbox-Retry greift; bei 5 Fehlern → DLQ
- [ ] Settings FEDERATION Tab zeigt alle bekannten Peers mit Status
- [ ] `direct_mesh`: Node-Discovery aus `peers.yaml` funktioniert ohne Hive Station
- [ ] `hub_assisted`: Node registriert sich bei Hive Station und erhält Peer-Liste/Presence
- [ ] Hive Station temporär offline: Node arbeitet mit lokalem Peer-Cache weiter
- [ ] `hub_relay` (wenn aktiviert): Peer-Update kann über Relay zugestellt werden und bleibt signaturgeprüft

---

## Key-Rotation — In-Flight-Nachrichten-Protokoll

`hivemind federation rotate-key` (CLI) führt folgende Schritte aus:

1. **Neues Keypair generieren** — in `node_identity` gespeichert (neuer `public_key`, alter Key als `previous_public_key` mit Timestamp)
2. **Grace-Period starten** (`HIVEMIND_KEY_ROTATION_GRACE_SECONDS`, Default: 3600 / 1h) — während dieser Zeit akzeptiert die Signatur-Middleware **sowohl** den alten als auch den neuen Public Key
3. **Neuen Public Key an Peers verteilen** — `POST /federation/key-update` an alle bekannten Peers (signiert mit **neuem** Private Key); Peers speichern beide Keys in `nodes.previous_public_key`
4. **Outbox-Einträge die vor Rotation in die Queue kamen** — sind mit dem alten Private Key signiert und werden während der Grace-Period von Peers noch akzeptiert (da `previous_public_key` noch gültig ist)
5. **Nach Grace-Period** — `previous_public_key` wird auf `NULL` gesetzt; Nachrichten mit altem Key → HTTP 401

> **DLQ-Umgang:** Wenn Outbox-Einträge mit altem Key in der DLQ landen (weil Grace-Period abgelaufen), müssen sie **re-signiert und re-queued** werden. CLI: `hivemind federation resign-dlq` — re-signiert alle DLQ-Einträge mit dem aktuellen Private Key und verschiebt sie zurück in `sync_outbox`.

## Abhängigkeiten

- Phase 2 abgeschlossen (Auth, Node-Keypair-Bootstrap)

## Öffnet folgende Phase

→ [Phase 3: MCP Read-Tools](./phase-3.md)
