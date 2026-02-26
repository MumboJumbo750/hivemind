# RBAC — Rollen & Berechtigungen

← [Index](../../masterplan.md)

---

## Actor-Modell

| Rolle | Beschreibung |
| --- | --- |
| `developer` | Lesen + Schreiben nur im eigenen Epic-Scope |
| `admin` | Globales Schreiben, Triagieren, Mergen |
| `service` | Technische Integrationen (Webhook-Ingest, CI/CD) mit minimalen Scopes — nur Reads, keine Writes |
| `kartograph` | Globales Lesen ohne Kontextfilter, Schreiben von Wiki + Docs |

> **`service` Rolle — Zweck:** Die `service`-Rolle ist für automatisierte technische Integrationen vorgesehen, z.B. YouTrack-Webhook-Ingest, Sentry-Webhook-Ingest oder CI/CD-Pipelines die Task-Status prüfen. Service-Accounts haben nur minimale Leserechte (`get_epic`, `get_task`) und **keine Schreibrechte**. Der Webhook-Ingest-Endpoint selbst ist ein interner Backend-Prozess (kein MCP-Call) — der `service`-Actor wird nur für Audit-Purposes als Actor im `mcp_invocations`-Log geführt. Service-Accounts authentifizieren sich via API-Key (kein Passwort/JWT).

Rollen können **pro Projekt überschrieben** werden (via `project_members.role`).

### Präzedenz-Regel: Global vs. Projekt-lokal

`project_members.role` überschreibt `users.role` **nur für projekt-scoped Aktionen**:

- **Projekt-scoped (überschreibbar):** Aktionen auf Epics, Tasks, Docs, Skills mit `project_id` — hier gilt die Projekt-Rolle aus `project_members.role`
- **Global-only (nicht überschreibbar):** Die folgenden Permissions erfordern **immer** `users.role = 'admin'` — unabhängig von `project_members.role`:
  - `triage` / `read_audit_log` — sehen alle Projekte, können nicht projekt-lokal gewährt werden
  - `merge_skills`, `reject_skill`, `accept_skill_change`, `reject_skill_change` — globale Skill-Verwaltung
  - `merge_guard`, `reject_guard`, `accept_guard_change`, `reject_guard_change` — globale Guard-Verwaltung
  - `reassign_owner` — kann Epics projekt-übergreifend beeinflussen

> **Phase F:** `list_peers` ist global (kein Projekt-Scope) — alle Rollen außer `service` dürfen Peers einsehen. `manage_discovery_sessions` (start/end) ist auf `kartograph` und `admin` beschränkt.

**Beispiel:** Ein User mit `users.role = 'developer'` und `project_members.role = 'admin'` in Projekt A hat erhöhte Rechte **nur innerhalb von Projekt A** (z.B. `cancel_task`, `resolve_decision_request` für alle Epics des Projekts). Globale Admin-Funktionen (Triage, Audit Log, Skill-/Guard-Merge) sind weiterhin nicht erreichbar — dafür muss `users.role = 'admin'` gesetzt sein.

---

## Berechtigungsmatrix

| Permission | developer | admin | service | kartograph |
| --- | --- | --- | --- | --- |
| `read_own_epic` | ✓ | ✓ | ✓ | ✓ |
| `read_any_epic` | — | ✓ | — | ✓ |
| `read_any_wiki` | ✓ | ✓ | — | ✓ |
| `read_any_skill` | ✓ | ✓ | — | ✓ |
| `read_any_doc` | ✓ | ✓ | — | ✓ |
| `context_boundary_filter` | aktiv | aktiv | aktiv | **deaktiviert** |
| `write_tasks` | eigene Epics | alle | — | — |
| `assign_task` | eigene Epics | alle | — | — |
| `write_wiki` | — | ✓ | — | ✓ |
| `write_epic_docs` | — | ✓ | — | ✓ |
| `propose_skill` | ✓ | ✓ | — | — |
| `fork_federated_skill` | ✓ | ✓ | — | — |
| `propose_skill_change` | ✓ | ✓ | — | — |
| `submit_skill_proposal` | ✓ | ✓ | — | — |
| `merge_skills` | — | ✓ | — | — |
| `reject_skill` | — | ✓ | — | — |
| `accept_skill_change` | — | ✓ | — | — |
| `reject_skill_change` | — | ✓ | — | — |
| `reject_guard` | — | ✓ | — | — |
| `manage_epic_restructure` | — | ✓ | — | — |
| `propose_guard` | ✓ | ✓ | — | ✓ |
| `propose_guard_change` | ✓ | ✓ | — | ✓ |
| `submit_guard_proposal` | ✓ | ✓ | — | ✓ |
| `merge_guard` | — | ✓ | — | — |
| `accept_guard_change` | — | ✓ | — | — |
| `reject_guard_change` | — | ✓ | — | — |
| `route_event` | — | ✓ | — | — |
| `ignore_event` | — | ✓ | — | — |
| `requeue_dead_letter` | — | ✓ | — | — |
| `resolve_escalation` | — | ✓ | — | — |
| `assign_bug` | — | ✓ | — | — |
| `reassign_owner` | — | ✓ | — | — |
| `resolve_decision_request` | Owner-Epics | ✓ | — | — |
| `cancel_task` | — | ✓ | — | — |
| `triage` | — | ✓ | — | — |
| `read_audit_log` | — | ✓ | — | — |
| `propose_epic_restructure` | — | — | — | ✓ |
| `execute_tasks` | ✓ | ✓ | — | — |
| `list_peers` | ✓ | ✓ | — | ✓ |
| `manage_discovery_sessions` | — | ✓ | — | ✓ |

---

## Kartograph — Sonderfall

```json
{
  "role": "kartograph",
  "permissions": {
    "read_any_epic": true,
    "read_any_wiki": true,
    "read_any_skill": true,
    "read_any_doc": true,
    "context_boundary_filter": false,
    "write_wiki": true,
    "write_epic_docs": true,
    "propose_epic_restructure": true,
    "propose_guard": true,
    "propose_guard_change": true,
    "write_tasks": false,
    "execute_tasks": false,
    "merge_skills": false,
    "merge_guard": false,
    "cancel_task": false
  }
}
```

`context_boundary_filter: false` bedeutet: Bibliotekar-Filterung wird für den Kartographen **deaktiviert**. Er bekommt auf Anfrage alles — muss es aber aktiv anfragen (Fog of War bleibt).

---

## Scope-Regeln für `write_tasks`

`developer` darf Tasks schreiben (`write_tasks`) wenn **mindestens eine** der folgenden Bedingungen gilt:

1. Der User ist `project_member` im Projekt des Epics (unabhängig von Epic-Ownership)
2. Der User ist `assigned_to` auf dem spezifischen Task → darf **diesen** Task schreiben

**Konsequenz für Task-Zuweisung:** Ein Developer der via `assigned_to` zu einem Task zugeteilt wird, erhält damit automatisch Schreibrecht auf genau diesen Task — auch wenn er kein `project_member` des Projekts ist. Admins und Owners können Tasks epics-weit zuweisen.

---

## Governance-Regeln

- Agenten handeln immer im Namen eines Actors
- Skill-Aktivierung nur per Admin-Merge
- Kein direkter Write in globale Skills ohne Proposal-Flow
- Jeder Write erzeugt Audit-Eintrag mit Vorher/Nachher-Diff

---

## Audit-Retention

| Daten | Retention | Verhalten nach Ablauf |
| --- | --- | --- |
| Volle Payload (input + output) | 90 Tage (`AUDIT_RETENTION_DAYS`) | `input_payload` + `output_payload` → `null` |
| Summary (actor, tool, timestamp, status, epic_id) | 1 Jahr | Record bleibt, nur Payload genullt |
| Record selbst | Unbegrenzt | Nie löschen |

Täglicher Archivierungs-Cron-Job im Backend.
