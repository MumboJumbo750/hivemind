# Federation — Die Gilde

← [Index](../../masterplan.md)

**Verfügbar ab:** Phase F (Core-Feature, nach Phase 2)
**Voraussetzung:** Alle Nodes im selben VPN-Netzwerk, Phase 2 abgeschlossen

---

## Vision

Hivemind ist kein Tool — es ist eine Welt. Jeder Entwickler ist ein **Kommandant** mit eigener Basis (Node), eigenem Arsenal (Skills) und eigenem Schwarm (Worker-Agenten). Federation verbindet diese Basen zu einer **Gilde**.

```text
Ohne Federation:         Mit Federation:
┌──────────────┐         ┌────────┐  ┌────────┐  ┌────────┐
│  Alex        │         │ Alex   │──│  Ben   │──│ Clara  │
│  [isoliert]  │    →    │ [Base] │  │ [Base] │  │ [Base] │
└──────────────┘         └────────┘  └────────┘  └────────┘
                                  Geteilte Karte
                                  Geteilte Skills
                                  Verteilte Quests
```

### Die Kernmetaphern

| Spielwelt | Hivemind-Konzept |
| --- | --- |
| **Gilde** | Federation — verbundene Nodes im VPN |
| **Kommandant** | Entwickler mit eigenem Node |
| **Base / Outpost** | Hivemind-Instanz (eigene DB, eigenes Docker) |
| **Mercenary** | Worker-Agent (AI-Client) |
| **Loadout** | Skill-Set das einem Worker vor einer Quest angepinnt wird |
| **Quest** | Task — klare Mission, DoD, Artifact als Loot |
| **Weltkarte** | Nexus Grid — gemeinsam exploriert, Fog of War |
| **Scout** | Kartograph — erkundet die Karte, lichtet Fog of War |
| **Wissensbibliothek** | Federated Skills + Wiki — Gildenwissen für alle verfügbar |

---

## Konzept

Jeder Entwickler betreibt seine eigene vollständige Hivemind-Instanz. Nodes kennen sich und können:

- **Skills & Wiki-Artikel** teilen (Push-basiert, opt-in per `federation_scope`)
- **Epics teilen** — Sub-Tasks können einem Peer-Node zugewiesen werden
- **Task-State-Updates** austauschen — Origin-Node sieht Fortschritt über alle Peers
- **Kartograph-Discoveries** teilen — die Weltkarte wächst kollektiv

**Origin-Authority:** Jede Entität hat einen `origin_node_id`. Nur der Origin-Node kann editieren. Peers erhalten Read-only-Kopien.

---

## Node-Identität

Jede Hivemind-Instanz hat eine eindeutige Identität (wird beim ersten Start in `node_identity` auto-generiert):

```text
node_id:    UUID (wird nie geändert)
node_name:  "alex-hivemind" (frei wählbar, human-readable)
node_url:   "http://192.168.1.10:8000" (VPN-IP + Port)
keypair:    Ed25519 (Private Key at-rest via HIVEMIND_KEY_PASSPHRASE verschlüsselt)
```

**Key-Exchange:** Beim manuellen Hinzufügen eines Peers wird dessen Public Key eingetragen (`nodes.public_key`). Alle ausgehenden Nachrichten werden mit dem eigenen Private Key signiert. Empfänger verifizieren gegen den hinterlegten Public Key.

### Key-Rotation & Revocation

Ein Schlüsseltausch ist notwendig wenn der Private Key kompromittiert wurde, der Node migriert wird oder ein regelmäßiger Rotation-Zyklus gewünscht ist.

```text
1. Neues Ed25519-Keypair generieren:
   → hivemind federation rotate-key

2. Neuen Public Key an alle bekannten Peers übermitteln:
   → Backend sendet POST /federation/ping (enthält neuen Public Key)
   → Peers aktualisieren nodes.public_key für diesen Node

3. Grace-Period (HIVEMIND_KEY_ROTATION_GRACE_SECONDS, Default: 3600):
   → Während der Grace-Period akzeptiert der eigene Node noch Nachrichten
     die mit dem alten Key signiert wurden (Peers noch nicht aktualisiert)
   → Nach Ablauf: alter Key wird verworfen

4. Revocation (sofortiger Entzug ohne Rotation):
   → hivemind federation revoke-key --peer <node_id>
   → nodes.public_key für diesen Peer → NULL
   → Alle eingehenden Nachrichten von diesem Peer → HTTP 401 (Key unknown)
   → Empfohlen bei Kompromittierung oder dauerhaftem Offboarding
```

| Kommando | Wirkung |
| --- | --- |
| `hivemind federation rotate-key` | Neues Keypair generieren + an alle Peers publishen |
| `hivemind federation revoke-key --peer <id>` | Public Key eines Peers widerrufen (sofort, keine Grace-Period) |
| `hivemind federation show-key` | Eigenen Public Key anzeigen (für manuellen Austausch) |

> **Backup:** Der Private Key wird AES-256-GCM-verschlüsselt mit `HIVEMIND_KEY_PASSPHRASE` gespeichert. Vor einer Rotation sollte ein verschlüsseltes Backup des alten Keys angelegt werden (`hivemind federation export-key --encrypted`), damit Audit-Logs die alte Signatur noch verifizieren können.

### Key-Kompromittierung — Notfallprozedur

Wenn ein Private Key kompromittiert wurde, muss sofort gehandelt werden. Die reguläre Rotation mit Grace-Period ist **nicht ausreichend**, da ein Angreifer während der Grace-Period gefälschte Nachrichten signieren könnte.

```text
1. SOFORT: Alle Peers revoken den kompromittierten Public Key
   → Admin auf JEDEM Peer: hivemind federation revoke-key --peer <kompromittierte_node_id>
   → Alternativ Broadcast: POST /federation/emergency-revoke (signed by kompromittierte Node, NOT)
   → Sicherste Variante: Manuell-koordinierte Revocation (Telefon/Chat)

2. Kompromittierter Node: Komplettes Key-Reset
   → hivemind federation rotate-key --no-grace  (Grace-Period = 0)
   → HIVEMIND_KEY_PASSPHRASE ändern
   → Neuen Public Key manuell an jeden Peer übermitteln (nicht über Federation!)
   → Manuelle Übermittlung zwingend — Federation-Kanal ist kompromittiert

3. Audit: Nachrichten seit Kompromittierung prüfen
   → SELECT * FROM sync_outbox
     WHERE direction = 'peer_inbound'
       AND created_at > :estimated_compromise_time
       AND JSON_EXTRACT(payload, '$.signing_node_id') = :compromised_node_id
   → Verdächtige Einträge: state → 'quarantined' (neuer State)
   → Triage-Items erzeugen für manuelle Prüfung

4. Entitäten-Audit:
   → Alle Entitäten mit origin_node_id = kompromittierter Node prüfen
   → Skills, Wiki, Code-Nodes: Letzte Änderungen nach Kompromittierungszeitpunkt
     flaggen und manuell reviewen
   → Bei Zweifeln: Entität auf letzten vertrauenswürdigen Stand zurücksetzen
     (version vor Kompromittierung)

5. Recovery-Bestätigung:
   → Kompromittierter Node sendet mit neuem Key POST /federation/ping
   → Jeder Peer trägt neuen Public Key ein und bestätigt
   → Full-Sync (GET /federation/sync?since=0) um sauberen State herzustellen
```

| Schritt | Verantwortlich | Zeitrahmen |
| --- | --- | --- |
| Revoke auf allen Peers | Jeder Peer-Admin | < 15 Minuten |
| Key-Reset auf kompromittiertem Node | Node-Owner | < 30 Minuten |
| Manueller Key-Austausch | Alle Beteiligten | < 1 Stunde |
| Audit + Quarantäne | Node-Owner | < 24 Stunden |
| Full-Sync + Bestätigung | Automatisch nach Key-Akzeptanz | Minuten |

> **Wichtig:** Federation über unsichere Kanäle (nicht-VPN) erhöht das Kompromittierungsrisiko. Bei Hub-Relay-Topologie muss auch der Hub-Key geprüft werden. Die Hive Station hat **keine** Signing-Keys — sie ist kein Angriffsvektor für gefälschte Entitäten, aber ein kompromittierter Hub könnte falsche Peer-Discovery-Informationen liefern.

---

## Peer Discovery

Federation unterstützt mehrere Discovery-Wege, die kombinierbar sind:

**1) Direkt: `peers.yaml`** (statische Konfiguration für VPN):

```yaml
peers:
  - name: ben-hivemind
    url: http://192.168.1.11:8000
    public_key: "ed25519:pub:AbCdEfGh..."
  - name: clara-hivemind
    url: http://192.168.1.12:8000
    public_key: "ed25519:pub:XyZw12..."
```

**2) Optional: Hive Station Bootstrap** (zentraler Registry/Presence-Dienst):

- Node registriert sich bei der Station und lädt bekannte Peers
- Station liefert Discovery + Status, aber bleibt ohne Schreibhoheit auf Hivemind-Entitäten
- Payloads zwischen Nodes bleiben Ed25519-signiert; Origin-Authority bleibt bei den Nodes

**3) Sekundär: mDNS** (automatische Discovery im LAN, optional via `HIVEMIND_MDNS_ENABLED=true`).
Neu entdeckte Nodes erscheinen zur manuellen Bestätigung in den Settings (Tab: FEDERATION).

---

## Topologie-Modi

| Modus | Discovery | Datenpfad | Vorteile |
| --- | --- | --- | --- |
| `direct_mesh` | `peers.yaml` (+ optional mDNS) | Direkt Node -> Node | Einfach, transparent, keine zentrale Abhängigkeit |
| `hub_assisted` | Hive Station + lokaler Peer-Cache | Direkt Node -> Node | Weniger manuelle Peer-Pflege, zentrale Presence |
| `hub_relay` | Hive Station + lokaler Peer-Cache | Direkt bevorzugt, optional über Station-Relay | Robuster bei instabilen Verbindungen |

**Hive Station ist Control Plane, nicht Data Plane.**  
Sie koordiniert Discovery/Presence (und optional Relay), aber sie ist nie Origin einer Epic/Task/Skill/Wiki-Entität.

> **Hive Station — Scope-Abgrenzung:** Die Hive Station ist ein **separates Projekt** mit eigener Codebasis, eigenem Deployment und eigenem Sicherheitsmodell. Hivemind-Docs spezifizieren nur die Client-seitige Integration (Registrierung, Presence-Abfrage, Relay-Nutzung). API-Spezifikation, Deployment-Anleitung und Sicherheitsmodell der Hive Station werden in einem dedizierten Repository dokumentiert (`hive-station/`). Hivemind funktioniert vollständig ohne Hive Station (`direct_mesh`-Topologie).

---

## Was wird geteilt?

| Kategorie | Inhalt | Scope | Wer kann editieren |
| --- | --- | --- | --- |
| **LOCAL** | Tasks, Epics, Audit-Logs, Drafts | Nur diese Node | Diese Node |
| **FEDERATED** | Skills (`federation_scope='federated'`), Wiki-Artikel | Push zu allen Peers | Nur Origin-Node |
| **SHARED EPIC** | Epics + zugewiesene Sub-Tasks | Multi-Node sichtbar | Origin-Node besitzt Epic-State |

### Federation-Scope Default-Asymmetrie (intentional)

Nicht alle Entitäten haben denselben `federation_scope`-Default — das ist bewusste Designentscheidung:

| Entitätstyp | Default `federation_scope` | Rationale |
| --- | --- | --- |
| `code_nodes` / `code_edges` | `'federated'` | **Karte ist immer kollektiv.** Der Kartograph erkundet für die Gilde — seine Discoveries sind per Definition geteiltes Wissen. Kein Opt-in nötig. |
| `skills` | `'local'` | **Wissen ist proprietär by default.** Ein Skill repräsentiert Teamkonventionen die möglicherweise project-specific oder nicht für andere Nodes relevant sind. Sharing ist explizites Opt-in. |
| `wiki_articles` | `'local'` | Wie Skills — globales Wissen nur teilen wenn es wirklich gildenrelevant ist. |
| `epics` / `tasks` | `'local'` | Epics sind immer Origin-lokal. Task-Delegation an Peers läuft über den Shared-Epic-Flow, nicht über `federation_scope`. |

**Kurzregel:**

- Kartograph-Discoveries → immer federated (geteilte Weltkarte ist das Ziel)
- Skills, Wiki → opt-in federated (Admin setzt `federation_scope = 'federated'` explizit)

---

## Federation Protocol

Alle Endpoints unter `/federation/*` (FastAPI, Port identisch mit Haupt-API):

| Endpoint | Methode | Beschreibung |
| --- | --- | --- |
| `/federation/ping` | POST | Node-Discovery, Heartbeat, gibt Public Key zurück |
| `/federation/skill/publish` | POST | Skill (active + federated) an Peer senden |
| `/federation/skill/propose_change` | POST | Skill-Change-Proposal von Peer-Node an Origin-Node weiterleiten |
| `/federation/wiki/publish` | POST | Wiki-Artikel (federated) an Peer senden |
| `/federation/epic/share` | POST | Epic + zugewiesene Task-Specs an Peer senden |
| `/federation/task/update` | POST | Task-State-Update zurück an Origin-Node |
| `/federation/code_discovery` | POST | Code-Node + Edges (Kartograph-Discovery) an Peer senden |
| `/federation/discovery_session` | POST | Discovery-Session-Ankündigung (type='start'\|'end') an alle Peers |
| `/federation/sync` | GET | Pull-Sync: alle Änderungen seit `?since=<timestamp>` |

**Authentifizierung:**
Jede Nachricht enthält einen `X-Hivemind-Signature` Header (Ed25519-Signatur über Body-Hash).
Backend prüft Signatur gegen `nodes.public_key` → unbekannte oder ungültige Signatur → HTTP 401.

---

## Shared Epic Flow

```text
1. Alex erstellt EPIC-7 mit TASK-1, TASK-2, TASK-3 (auf seinem Node)
   epics.origin_node_id = alex's node_id

2. Alex weist TASK-2 Ben zu:
   tasks.assigned_node_id = ben's node_id
   → Backend erzeugt sync_outbox-Eintrag:
       direction = 'peer_outbound'
       entity_type = 'epic_share'
       target_node_id = ben's node_id
       payload = { epic_spec, task_specs: [TASK-2] }

3. Outbox-Consumer sendet POST /federation/epic/share an ben-hivemind

4. Ben empfängt:
   → Erstellt lokale Kopien (epics + tasks) mit origin_node_id = alex's node_id
   → TASK-2 erscheint in Bens Prompt Station

5. Ben arbeitet TASK-2 ab (lokal, vollständig durch Review Gate)
   TASK-2 → in_review → done

6. Bens Node sendet POST /federation/task/update an Alex:
   payload = { task_id, new_state: 'done', result, artifacts }

7. Alex empfängt:
   → Spiegelt TASK-2 state auf seinem Node
   → Epic-Fortschritt sichtbar: TASK-1 ✓, TASK-2 ✓ (◈ ben-hivemind), TASK-3 pending
```

### `assigned_to` vs. `assigned_node_id` — Semantik bei Federation

Bei der Delegation von Tasks an Peer-Nodes gibt es zwei orthogonale Zuweisungskonzepte:

| Feld | Typ | Bedeutung | Beispiel |
| --- | --- | --- | --- |
| `tasks.assigned_to` | `UUID → users(id)` | **Lokaler User** der den Task bearbeitet. Immer eine lokale User-ID (nie ein Fremd-Node-User). | Ben's lokaler Solo-User |
| `tasks.assigned_node_id` | `UUID → nodes(id)` | **Peer-Node** auf dem der Task bearbeitet wird. NULL = lokaler Bearbeitung. | Ben's Node-ID |

**Ablauf bei Peer-Delegation:**

```text
1. Origin-Node (Alex) setzt:
   tasks.assigned_node_id = ben's node_id
   tasks.assigned_to = NULL  (Alex kennt Bens lokale User nicht)

2. Peer-Node (Ben) empfängt Task via epic_share:
   → Erstellt lokale Kopie mit origin_node_id = alex's node_id
   → tasks.assigned_to = bens lokaler Solo-User (automatisch)
   → tasks.assigned_node_id = NULL (auf Bens Node ist es ein lokaler Task)

3. Status-Sync via task_update:
   → Ben's Node → Alex's Node: { task_id, new_state, assigned_to: NULL }
   → assigned_to wird NICHT synchronisiert (lokales Konzept)
   → Alex sieht: TASK-2 state=done, assigned_node_id=ben's node_id
```

**Sonderfälle:**

| Szenario | `assigned_to` | `assigned_node_id` | Verhalten |
| --- | --- | --- | --- |
| Lokaler Task (kein Federation) | Lokaler User | `NULL` | Normaler Solo/Team-Betrieb |
| An Peer delegiert (auf Origin) | `NULL` | Peer Node-ID | Origin sieht "delegiert an [Peer]" |
| Empfangener Task (auf Peer) | Peer's lokaler User | `NULL` | Peer bearbeitet lokal |
| Rückdelegation an Origin | Lokaler User | `NULL` | `assigned_node_id` auf NULL, `assigned_to` auf lokalen User setzen |
| Peer offline, Task reassign | Neuer User / neuer Peer | Ggf. neuer Node | Triage-Item erzeugt; Admin weist manuell zu |

> **Prinzip:** `assigned_to` ist immer eine Node-lokale User-ID. Niemals werden User-IDs über Federation synchronisiert — jeder Node hat seine eigene User-Verwaltung. `assigned_node_id` ist das Federation-Routing-Feld.

---

## Mercenary Loadout Flow

Der wichtigste Moment bevor eine Quest beginnt: **den Mercenary ausrüsten**.

```text
Quest: TASK-42 "Implement JWT Refresh Token"
Epic:  EPIC-7 "Auth-System"

Architekt pinnt Skills (Loadout zusammenstellen):
  pinned_skills = [
    { skill_id: "fastapi-auth",      version: 3 },  ← von Alex's Node
    { skill_id: "jwt-patterns",      version: 2 },  ← von Ben's Node (federated)
    { skill_id: "pydantic-v2",       version: 1 },  ← global
  ]

Prompt Station zeigt:
  "Worker-Einsatz bereit"
  Loadout: FastAPI Auth (v3) + JWT Patterns (v2) + Pydantic v2 (v1)
  Guards: ruff check . | pytest tests/unit/ | no hardcoded secrets
  Token-Budget: 1020 / 8000

Ben öffnet seinen AI-Client, kopiert den Prompt → Worker bekommt exaktes Arsenal
```

**Warum federated Skills hier glänzen:** Ben kann einen Skill den Alex in einem anderen Projekt perfektioniert hat direkt in seinem Loadout nutzen — ohne Copy-Paste, mit Versionsbindung.

---

## Skill/Wiki Federation Flow

```text
1. Alex erstellt Skill "FastAPI Auth Pattern" → lifecycle: active
   Admin setzt federation_scope = 'federated'

2. Backend generiert pro bekanntem Peer einen sync_outbox-Eintrag
   (direction='peer_outbound', entity_type='skill')

3. Peers empfangen Skill:
   → Speichern lokal mit origin_node_id = alex's node_id
   → Skill ist read-only (kein Edit-Button in Skill Lab für fremde Skills)
   → Bibliothekar kann den Skill verwenden

4. Ben möchte den Skill anpassen:
   Option A: Lokaler Fork via MCP:
             hivemind/fork_federated_skill {
               "source_skill_id": "<uuid-origin-skill>",
               "target_project_id": "uuid|null"
             }
             → erstellt lokalen Draft-Skill mit extends=[origin_skill_id]
   Option B: Skill-Change-Proposal an Origin-Node weiterleiten
             → hivemind/propose_skill_change { "skill_id": "<federated-skill-uuid>", ... }
             → Backend erkennt: skill.origin_node_id ≠ eigene node_id
             → Erzeugt sync_outbox-Eintrag:
                 direction = 'peer_outbound'
                 entity_type = 'skill_change_proposal'
                 target_node_id = origin_node_id (= Alex)
                 payload = { proposal_spec, proposer_node_id, proposer_user }
             → Outbox-Consumer sendet POST /federation/skill/propose_change an Alex
             → Alex's Node empfängt Proposal, legt skill_change_proposal lokal an
             → Proposal erscheint in Alex's Triage Station → normaler Merge-Flow
             → Nach Merge: Alex pusht neue Skill-Version an alle Peers (inkl. Ben)

5. Alex merged neue Version:
   → erneuter Push an alle Peers (Versionsnummer steigt)
   → Peers aktualisieren lokale Kopie
```

UI-Hinweis: Der Button `[ÜBERNEHMEN]` in Gilde/Arsenal ruft `hivemind/fork_federated_skill` auf.

---

## Offline-Verhalten & Konflikt-Strategie

| Szenario | Verhalten |
| --- | --- |
| Peer offline beim Skill-Push | `sync_outbox` puffert (peer_outbound), Retry mit Exponential Backoff |
| Task-Update kommt verspätet an | Akzeptiert wenn `tasks.version` kompatibel; sonst manuelle Auflösung in Triage |
| Peer versucht federierten Skill zu editieren | HTTP 403 — nur Origin-Node darf editieren |
| Origin-Node dauerhaft offline | Federated Copies bleiben read-only; kein automatischer Ownership-Transfer |
| Netzwerk-Partition während Epic-Sharing | Origin-Node sieht Task als "pending sync" bis Peer wieder erreichbar |
| Hive Station nicht erreichbar | Fallback auf letzten lokalen Peer-Stand (`nodes` + `peers.yaml`) |

**Peer-Offline-Erkennung:** Der Heartbeat-Job sendet alle `HIVEMIND_FEDERATION_PING_INTERVAL` Sekunden (Default: 60s) ein POST `/federation/ping` an jeden Peer. Nach `HIVEMIND_FEDERATION_OFFLINE_THRESHOLD` verfehlten Heartbeats (Default: 3) wird `nodes.status → 'inactive'` gesetzt und eine Admin-Notification erzeugt. Der Peer-Status springt automatisch zurück auf `active` sobald ein Ping erfolgreich ist (kein manuelles Eingreifen nötig).

**Philosophie:** Origin-Authority statt Distributed Consensus → keine CRDTs, keine Vector Clocks, keine komplexe Merge-Logik.

### Concurrent State Transitions bei Shared Epics

Wenn zwei Nodes gleichzeitig State-Transitions auf denselben Shared-Task versuchen, greift **Origin-Authority mit Optimistic Locking**:

```text
Szenario: Ben (Peer) und Alex (Origin) ändern TASK-2 fast gleichzeitig

1. Ben: TASK-2 in_progress → in_review  (Bens lokaler State)
   → Ben sendet POST /federation/task/update { task_key, new_state: 'in_review', expected_version: 5 }

2. Alex: TASK-2 in_progress → blocked    (Alex setzt lokal Decision Request)
   → Alex hat Origin-Authority → schreibt direkt, version 5 → 6

3. Bens Update kommt an bei Alex:
   → expected_version: 5 ≠ aktuelle version: 6
   → HTTP 409 Conflict zurück an Ben
   → Ben erhält aktuellen State (blocked, version 6) in der 409-Response

4. Bens Node aktualisiert lokalen State auf 'blocked' (version 6)
   → Triage-Item auf Bens Node: "Task-State-Konflikt gelöst — TASK-2 ist jetzt 'blocked'"
```

**Regeln:**

| Regel | Beschreibung |
| --- | --- |
| **Origin-Wins** | Bei Version-Konflikten hat die Origin-Node den autoritativen State. Peers übernehmen |
| **Optimistic Locking** | Alle `/federation/task/update`-Calls senden `expected_version`; Mismatch → 409 |
| **Keine parallele Task-Bearbeitung** | Ein Shared-Task hat genau einen `assigned_node_id` — nur diese Node darf State-Transitions ausführen |
| **State-Sync bei Reconnect** | Nach Netzwerk-Partition holt sich der Peer via `GET /federation/sync?since=<last_seen>` alle verpassten Updates |
| **Triage bei unlösbarem Konflikt** | Falls ein `409` nach 3 automatischen Retries nicht auflösbar ist → `sync_dead_letter` + Triage-Item |

### Peer-Entfernung / Offboarding

Wenn ein Peer via `[ENTFERNEN]` oder `[BLOCKIEREN]` aus der Gilde entfernt wird, muss ein definierter Cleanup-Prozess greifen:

**`[BLOCKIEREN]` (reversibel):**

```text
1. nodes.status → 'blocked'
2. Alle ausstehenden sync_outbox-Einträge für diesen Peer → state: 'cancelled'
3. Keine neuen Outbound-Nachrichten an diesen Peer
4. Eingehende Nachrichten von diesem Peer → HTTP 403 (Signatur gültig, aber blocked)
5. Shared Epics: Tasks die auf dem blockierten Peer lagen → state: 'blocked' + Triage-Item
   "TASK-X war auf [blockierter Peer] — Neu zuweisen oder abbrechen?"
6. Federated Skills/Wiki von diesem Peer: bleiben als read-only Kopie (origin_node_id unverändert)
   Kein Auto-Delete — Owner kann manuell löschen
```

**`[ENTFERNEN]` (irreversibel, erfordert Admin-Bestätigung):**

```text
1. Alle Schritte von [BLOCKIEREN] +
2. nodes-Eintrag → status: 'removed' (nicht gelöscht — Audit-Trail)
3. Federated Skills/Wiki von diesem Peer:
   → Admin-Dialog: "3 Skills und 2 Wiki-Artikel von [Peer]. Behalten (ohne Updates) oder löschen?"
   → Bei 'Behalten': federation_scope → 'local', origin_node_id bleibt (für Provenance), kein Sync mehr
   → Bei 'Löschen': Soft-Delete (restore innerhalb 30 Tage möglich)
4. Code-Nodes mit origin_node_id = entfernter Peer: bleiben in der Karte (Fog of War nicht zurücksetzen)
5. sync_dead_letter-Einträge für diesen Peer: archiviert, nicht re-queueable
```

> **Wiederaufnahme:** Ein blockierter Peer kann über `[ENTSPERREN]` wieder aktiviert werden → Full-Sync. Ein entfernter Peer muss komplett neu hinzugefügt werden (neuer Key-Exchange).

> **Schema-Referenz Offboarding:** `nodes.status` unterstützt die Werte `active|inactive|blocked|removed` (→ [data-model.md](../architecture/data-model.md)). `sync_outbox.state` unterstützt `cancelled` für abgebrochene Outbound-Einträge. Soft-Delete für Skills/Wiki nutzt `nodes.deleted_at` (TIMESTAMPTZ) — Einträge mit `deleted_at IS NOT NULL` sind logisch gelöscht, bleiben aber für Audit lesbar und sind innerhalb von 30 Tagen wiederherstellbar.

---

## Federated Kartograph — Die gemeinsame Weltkarte

Der stärkste Anwendungsfall von Federation: **die Karte gemeinsam aufdecken**.

Jeder Kartograph erkundet seinen Teil der Codebase. Einzeln hat jeder nur ein Fragment. Zusammen entsteht eine vollständige Karte.

```text
Große Codebase: 500k LOC — zu groß für einen Kartographen

Alex erkundet:   auth/ + api/        → 120 code_nodes, 340 code_edges
Ben erkundet:    worker/ + queue/    → 80 code_nodes,  210 code_edges
Clara erkundet:  frontend/ + tests/  → 150 code_nodes, 480 code_edges

Federated Nexus Grid = 350 code_nodes, 1030 code_edges
→ Fast vollständige Karte; Fog of War gemeinsam gelichtet
```

### Discovery Federation Protocol

```text
Kartograph erkundet neuen Code-Node auf Alex's Node:
  → code_nodes.origin_node_id = alex's node_id
  → code_nodes.federation_scope = 'federated' (Kartograph-Discoveries sind Default federated)
  → Backend erzeugt sync_outbox-Eintrag (peer_outbound, entity_type='code_discovery')
  → Peers empfangen Node + Edges
  → Jeder Peer hat nun denselben Code-Node in seinem Nexus Grid
  → Fog of War auf allen Nodes gelichtet
```

### Discovery Session (Anti-Doppelarbeit)

Wenn Ben und Clara gleichzeitig dieselbe Codebase explorieren ohne es zu wissen — Verschwendung. Die **Discovery Session** verhindert das:

```text
Clara startet Exploration von frontend/:
  → Markiert "exploring: frontend/" auf ihrem Node
  → Federation pusht: { type: 'discovery_session', area: 'frontend/', node: 'clara' }
  → Ben sieht im Nexus Grid: [◈ clara erkundet frontend/ ...]
  → Ben wählt worker/ statt frontend/ → kein Doppelaufwand
```

Datenmodell: `code_nodes.explored_by` + neues Feld `exploring_node_id` (temporär, NULL nach Abschluss).

> **Lokale Doppelarbeit:** `exploring_node_id` verhindert nur Federation-Doppelarbeit (Cross-Node). Wenn zwei manuelle Kartograph-Prompts auf **derselben Node** gleichzeitig denselben Code-Bereich explorieren, gibt es keinen lokalen Lock-Mechanismus. **Mitigation:** Die Prompt Station zeigt aktive Kartograph-Sessions an; der Prompt-Generator warnt wenn bereits ein Kartograph-Prompt für denselben `path`-Prefix generiert wurde (Best-Effort, kein Hard-Lock). Für Phase 8 (Autonomie) ist ein Advisory-Lock (`pg_advisory_xact_lock` auf `hashtext(path_prefix)`) evaluierbar.

---

## Phase-3-Bonus: Federated Semantic Search

Ab Phase 3 (Ollama) ist optional möglich:

```text
Bibliothekar sucht Skill via Embedding-Similarity:
  → Lokale Suche auf dieser Node
  → Falls aktiviert (HIVEMIND_FEDERATED_SEARCH=true):
      GET /federation/sync → aggregiert federated Skills von allen Peers
      Embeddings werden lokal gecacht (origin_node_id + version als Cache-Key)
      Re-Embedding nur wenn Peer meldet: neue Version vorhanden
```

> **⚠ Skalierungshinweis — Ollama als Single-Instance-Flaschenhals:** In der Federation läuft Ollama auf *jeder Node* lokal. Bei Federated Semantic Search muss jeder Node die Embeddings für empfangene Peer-Entitäten **lokal** berechnen (Re-Embedding bei Cache-Miss). Bei einer Gilde mit N Peers und M Entitäten ergibt sich ein O(N×ΔM)-Embedding-Aufwand pro Sync-Zyklus. **Mitigationen:** (1) Pre-computed Embeddings mit Peer-Nachrichten mitliefern (erfordert identisches Embedding-Modell auf allen Nodes — `embedding_model`-Feld in allen Embedding-Tabellen prüfen), (2) Embedding-Queue mit Batch-Verarbeitung und Priorität (lokale Entitäten > Peer-Entitäten), (3) `HIVEMIND_EMBEDDING_BATCH_SIZE` konservativ setzen bei schwacher GPU. Siehe auch [Bekannte Skalierungsgrenzen](../architecture/overview.md) ("Ollama Single Instance").

---

## Konfiguration

| Env-Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_FEDERATION_ENABLED` | `false` | Federation aktivieren |
| `HIVEMIND_FEDERATION_TOPOLOGY` | `direct_mesh` | `direct_mesh` \| `hub_assisted` \| `hub_relay` |
| `HIVEMIND_NODE_NAME` | `hivemind` | Human-readable Node-Name |
| `HIVEMIND_KEY_PASSPHRASE` | — | Passphrase für Private-Key-Verschlüsselung (Pflicht wenn Federation aktiv) |
| `HIVEMIND_PEERS_CONFIG` | `peers.yaml` | Pfad zur Peer-Konfigurationsdatei |
| `HIVEMIND_HIVE_STATION_URL` | — | URL der optionalen Hive Station (Control Plane) |
| `HIVEMIND_HIVE_STATION_TOKEN` | — | Optionales Auth-Token für Hive Station |
| `HIVEMIND_HIVE_RELAY_ENABLED` | `false` | Store-and-forward Relay über Hive Station erlauben |
| `HIVEMIND_MDNS_ENABLED` | `false` | mDNS-Discovery aktivieren |
| `HIVEMIND_FEDERATED_SEARCH` | `false` | Federated Semantic Search (ab Phase 3) |
| `HIVEMIND_FEDERATION_PING_INTERVAL` | `60` | Heartbeat-Intervall in Sekunden |
| `HIVEMIND_FEDERATION_OFFLINE_THRESHOLD` | `3` | Anzahl verfehlter Heartbeats bevor Peer als `inactive` markiert wird. Bei Ping-Intervall 60s entspricht `3` einem Timeout von ~3 Minuten. |
| `HIVEMIND_KEY_ROTATION_GRACE_SECONDS` | `3600` | Sekunden in denen der alte Key nach Rotation noch akzeptiert wird (für nicht-aktualisierte Peers) |
