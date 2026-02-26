# Phase 2 — Identity & RBAC

← [Phasen-Übersicht](./overview.md) | [Index](../../masterplan.md)

**Ziel:** Actor-Modell, Authentifizierung, Rollenbasierte Zugriffskontrolle, Audit-Log-Writing, Solo/Team-Modus aktiv.

**AI-Integration:** Keine. Alles läuft manuell über Chat.

---

## Deliverables

### Backend

- [ ] User-Registrierung + Login (JWT oder Session-basiert)
- [ ] Actor-Modell: `developer`, `admin`, `service`, `kartograph`
- [ ] Middleware: AuthN + AuthZ für alle Writes
- [ ] Scope-Validierung: Developer schreibt nur wenn `project_member` des Projekts ODER als `assigned_to` auf dem spezifischen Task (→ [rbac.md Scope-Regeln](../architecture/rbac.md))
- [ ] Optimistic Locking: `expected_version` auf allen mutierenden Write-Endpoints (bei Create-Writes auf der Parent-Entität)
- [ ] Idempotenz: `idempotency_key` auf allen Write-Endpoints
- [ ] Audit-Writer: jeder Write erzeugt Eintrag in `mcp_invocations`
- [ ] Solo-Modus: RBAC deaktiviert, System-User automatisch befüllt
- [ ] Team-Modus: RBAC aktiv, explizite Actor-Pflichtfelder
- [ ] `project_members` RBAC: Rolle pro Projekt überschreibt globale Rolle
- [ ] `app_settings`-Tabelle mit Solo/Team-Modus-Persistenz (Laufzeit-Switch)
- [ ] **Node-Bootstrap:** Beim ersten Start `node_identity` auto-generieren (UUID + Ed25519-Keypair via `cryptography`-Lib) + eigenen Node in `nodes`-Tabelle eintragen

### Frontend

- [ ] Login-Screen (sci-fi Stil — minimalistisch, kein generisches Form-Design)
- [ ] Actor-Identity-Badge im System Bar (Username + Rolle + Avatar-Placeholder)
- [ ] Solo/Team-Modus-Toggle in Settings (Laufzeit-Switch, kein Neustart nötig)
- [ ] Command Deck (erster Stand): Epic-Liste, Task-Übersicht, State-Badges
- [ ] Epic Scoping Modal (Owner, SLA, Priority, DoD-Rahmen)
- [ ] Task Review Panel (DoD-Checkliste, Approve/Reject) — zeigt nur DoD-Kriterien; Guard-Status kommt in Phase 5
- [ ] Task Review Panel strukturiert in **Hard Gates** (systemisch) und **Owner Judgment** (fachlich)
- [ ] Focus Mode (Prompt-Fokus): blendet Nav Sidebar + Status Bar temporaer aus, kritische Alerts bleiben sichtbar

> **Hinweis Phase 2–4:** Die `in_review`-Transition prüft in diesen Phasen **keine Guards**, da `report_guard_result` und `update_task_state`-Validierung erst in Phase 5 implementiert werden. Tasks können in Phase 2–4 ohne Guard-Prüfung nach `in_review` wechseln. Ab Phase 5 gilt: alle Guards müssen `passed|skipped` sein bevor `in_review` möglich ist.
> **Hard Gates in Phase 2-4:** technische Mindestpruefung bleibt auf `result`/State-Logik beschraenkt; Guard-Verifikation und Guard-Provenance greifen ab Phase 5.
- [ ] Notification Tray (🔔 Badge + Panel): SLA-Warnings, offene Actions
- [ ] SLA-Timer: Sichtbarer Countdown auf Epic- und Task-Ebene

---

## Technische Details

### JWT-Auth Flow

```text
POST /auth/login  { username, password }
→ { access_token, expires_in }

Header: Authorization: Bearer <token>
→ Backend extrahiert actor_id + actor_role aus Token (server-side source of truth)
→ Client-seitig mitgegebene actor_id/actor_role im Request-Body werden gegen Token-Claims validiert
→ Abweichung → HTTP 403 (kein Spoofing möglich)
```

### MCP Write-Pflichtfelder (ab Phase 2 enforced)

```json
{
  "request_id": "uuid",
  "actor_id": "uuid",
  "actor_role": "developer|admin|service|kartograph",
  "epic_id": "uuid",       // optional — nur bei Epic/Task-scoped Writes
  "idempotency_key": "uuid",
  "expected_version": 12
}
```

> `epic_id` ist **nicht global Pflicht**: Epic/Task-Writes erfordern es (Scope-Validierung); globale Writes wie `merge_skill`, `merge_guard`, `create_wiki_article` haben keinen Epic-Bezug und lassen `epic_id` leer. Das Backend prüft `epic_id` nur wenn das jeweilige Tool Epic-Scope verlangt.

### Solo-Modus-Vereinfachungen

```text
HIVEMIND_MODE=solo (Bootstrap-Default, danach DB-gesteuert):
  - RBAC deaktiviert (alle dürfen alles)
  - System-User "solo" wird automatisch als Actor eingesetzt
  - Review-Gate bleibt aktiv (kein direktes done)
  - Skill-Merge ohne Admin-Gate
  - Decision-Request ohne SLA-Timeout
```

### Audit-Retention-Cron (täglich)

```python
# Setzt input_payload + output_payload auf null
# für Einträge älter als AUDIT_RETENTION_DAYS
# Record selbst bleibt erhalten
```

---

## Acceptance Criteria

- [ ] Login funktioniert, Token wird ausgestellt
- [ ] Unauthentifizierter Write → HTTP 401
- [ ] Developer-Write ohne `project_member`-Zugehörigkeit und ohne `assigned_to` → HTTP 403
- [ ] Admin-Write überall → HTTP 200
- [ ] `expected_version` Mismatch → HTTP 409
- [ ] Gleiche `idempotency_key` zweimal → selbe Response, kein doppelter Write
- [ ] Jeder Write hat Eintrag in `mcp_invocations`
- [ ] Solo-Modus: RBAC-Checks übersprungen, aber Review-Gate aktiv
- [ ] Solo/Team-Switch in Settings funktioniert ohne Neustart
- [ ] Command Deck zeigt Epics + Tasks mit korrekten State-Badges
- [ ] Epic Scoping Modal setzt Epic auf `scoped`
- [ ] Review Panel zeigt DoD-Checkliste und ermöglicht Approve/Reject
- [ ] Review Panel zeigt getrennte Bereiche "Hard Gates" und "Owner Judgment"
- [ ] Focus Mode (Prompt-Fokus) funktioniert ohne Verlust kritischer Alerts
- [ ] Notification Tray zeigt SLA-Warnings

---

## Abhängigkeiten

- Phase 1 abgeschlossen (Datenschema, State Machine)

## Öffnet folgende Phasen

→ [Phase F: Federation](./phase-f.md) — kollaborative Karte, Skill-Loadouts, Gilde
→ [Phase 3: MCP Read-Tools](./phase-3.md)
