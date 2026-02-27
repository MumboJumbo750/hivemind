---
slug: "federation-konzept"
title: "Federation — Sovereign Nodes"
tags: ["federation", "p2p", "sovereign-nodes"]
linked_epics: ["EPIC-PHASE-F"]
---

# Federation — Sovereign Nodes

## Prinzip

Jeder Entwickler betreibt seine eigene Hivemind-Instanz. Nodes im selben VPN können Skills, Wiki-Artikel und Epics teilen und Tasks delegieren.

## Topologien

| Topologie | Beschreibung |
| --- | --- |
| `direct_mesh` | Alle Nodes kennen sich direkt (Default) |
| `hub_assisted` | Hub vermittelt Routing, Daten fließen direkt |
| `hub_relay` | Hub leitet alle Daten weiter (Firewall-Szenarien) |

## Sicherheit

- **Ed25519-Signaturen** auf allen Federation-Requests
- **Public Key Exchange** beim Peer-Handshake
- **Key Rotation** mit Grace Period für Übergang
- **Peer-Status:** active → inactive → blocked → removed

## Was kann geteilt werden?

| Entität | Shareable | Scope-Feld |
| --- | --- | --- |
| Skills | Ja | `federation_scope: 'federated'` |
| Wiki-Artikel | Ja | `federation_scope: 'federated'` |
| Epics | Ja (Share + Task-Delegation) | `origin_node_id` |
| Code-Nodes | Ja (Kartograph-Discovery) | `federation_scope: 'federated'` |

## Fork-Workflow (Skills)

```
Peer A publiziert Skill "FastAPI Auth" (federated)
  → Peer B sieht Skill in Gilde-View
  → Peer B klickt [ÜBERNEHMEN]
  → Lokaler Draft-Fork (extends: Origin-Skill)
  → Peer B passt an → merged lokal
```
