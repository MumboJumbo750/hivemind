---
epic_ref: "EPIC-PHASE-F"
title: "Phase F — Architektur-Kontext"
---

# Phase F — Federation

## Überblick

Phase F ermöglicht verteilte Hivemind-Instanzen: Jeder Entwickler betreibt seinen eigenen Sovereign Node. Nodes im selben VPN können Skills, Wiki-Artikel und Epics teilen und Sub-Tasks delegieren — peer-to-peer, ohne zentrale Autorität.

## Architektur-Entscheidungen

### Sovereign Nodes
Jede Hivemind-Instanz ist ein eigenständiger Node mit eigener UUID + Ed25519-Keypair. Kein Node hat Schreibzugriff auf andere — alles läuft über signierte HTTP-Requests.

### Drei Topologie-Modi
| Modus | Discovery | Transport |
| --- | --- | --- |
| `direct_mesh` | `peers.yaml` + optional mDNS | Direkt Node→Node |
| `hub_assisted` | Hive Station + lokaler Cache | Direkt Node→Node |
| `hub_relay` | Hive Station + lokaler Cache | Direkt bevorzugt, optional Relay |

### Outbox-Pattern für Federation
`sync_outbox` mit `direction='peer_outbound'`. Bei Skill-Merge + `federation_scope='federated'` → automatische Outbox-Einträge für alle bekannten Peers. Ed25519-Signierung aller Federation-Requests.

### Fork statt Kopie
Federated Skills werden nicht überschrieben — `hivemind-fork_federated_skill` erstellt einen lokalen Draft-Fork mit `extends`-Link zum Origin. Änderungen am Origin propagieren als Vorschlag, nicht als Overwrite.

### Epic-Share & Task-Delegation
`assigned_node_id` auf Tasks → Epic-Spec + Task-Spec wird an Peer-Node gesendet. Task-State-Updates vom Peer werden zurück-gespiegelt. Origin-Node bleibt Autoritiy.

## Key-Rotation-Protokoll

```
1. Neues Keypair generieren → node_identity
2. Grace-Period (Default: 1h): alter + neuer Key akzeptiert
3. POST /federation/key-update an alle Peers (signiert mit neuem Key)
4. In-Flight-Nachrichten mit altem Key: akzeptiert während Grace
5. Nach Grace: alter Key → NULL, alter Signatur → HTTP 401
```

## Relevante Skills
- `ed25519-signing` — Kryptographische Signierung
- `outbox-consumer` — Outbox-Verarbeitung
- `docker-service` — Docker Compose Override
- `fastapi-endpoint` — Federation-Endpoints
- `state-machine-transition` — Task-State-Spiegelung
- `sse-event-stream` — SSE für Federation-Events
