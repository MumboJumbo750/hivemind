---
title: "Notification-Dispatch bei State-Transitions"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.8
source_epics: ["EPIC-PHASE-5"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Notification-Dispatch bei State-Transitions

### Rolle
Du implementierst das Auslösen von Notifications bei relevanten State-Changes und Proposals.
Notifications werden in der Datenbank gespeichert und via SSE an verbundene Clients gesendet.

### Kontext

Hivemind benachrichtigt Nutzer über relevante Ereignisse: abgeschlossene Tasks,
neue Proposals die Review brauchen, Eskalationen. Phase 5 aktiviert die ersten
Notification-Types, die ab Phase 6 an einen dedizierten Notification-Service übergeben werden.

### Notification-Types (Phase 5)

| Type | Trigger | Empfänger | Payload |
| --- | --- | --- | --- |
| `task_done` | `approve_review` | Assignee + Owner | `{task_key, title}` |
| `guard_proposal` | `submit_guard_proposal` | Alle Admins | `{guard_id, title}` |
| `restructure_proposal` | `propose_epic_restructure` | Alle Admins | `{proposal_id, type, rationale}` |
| `skill_proposal` | `submit_skill_proposal` | Alle Admins | `{skill_id, title}` |
| `task_escalated` | `qa_failed_count >= 3` | Epic-Owner + Admins | `{task_key, reason}` |
| `decision_request` | `create_decision_request` | Epic-Owner | `{task_key, blocker}` |

### Konventionen

- Notifications werden **immer** in `notifications`-Tabelle gespeichert (durables Audit)
- SSE-Event wird **zusätzlich** gepusht an verbundene Clients des Empfängers
- Notification-Erstellung ist ein Side-Effect im Tool-Handler, kein separater Service-Call
- Event-Bus Pattern: `event_bus.publish(NotificationEvent(...))` → SSE-Adapter
- Notifications sind idempotent: `(type, entity_id, user_id)` als Dedup-Key
- `read_at` ist NULL bis User die Notification als gelesen markiert

### Datenmodell

```sql
CREATE TABLE notifications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id),  -- Empfänger
    type        TEXT NOT NULL,   -- 'task_done', 'guard_proposal', etc.
    entity_id   UUID,            -- Referenzierte Entität (Task, Skill, Guard, ...)
    payload     JSONB NOT NULL,  -- Type-spezifische Daten
    read_at     TIMESTAMPTZ,     -- NULL = ungelesen
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON notifications (user_id, created_at DESC);
CREATE INDEX ON notifications (user_id, read_at) WHERE read_at IS NULL;  -- Ungelesene
```

### Implementierung — Event-Bus-Pattern

```python
# services/notification_service.py

class NotificationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify(
        self,
        user_ids: list[UUID],
        type: str,
        entity_id: UUID | None,
        payload: dict,
    ) -> list[Notification]:
        """Erstellt Notifications für alle Empfänger + SSE-Push."""
        notifications = []
        for user_id in user_ids:
            # Dedup-Check
            existing = await self.db.scalar(
                select(Notification).where(
                    Notification.user_id == user_id,
                    Notification.type == type,
                    Notification.entity_id == entity_id,
                )
            )
            if existing:
                continue

            notification = Notification(
                user_id=user_id,
                type=type,
                entity_id=entity_id,
                payload=payload,
            )
            self.db.add(notification)
            notifications.append(notification)

            # SSE-Push an verbundene Clients
            await event_bus.publish_to_user(user_id, SSEEvent(
                event="notification",
                data={
                    "id": str(notification.id),
                    "type": type,
                    "payload": payload,
                    "created_at": notification.created_at.isoformat(),
                },
            ))

        return notifications

    async def notify_admins(self, type: str, entity_id: UUID, payload: dict):
        """Convenience: Benachrichtigt alle Admin-User."""
        admin_ids = await self._get_admin_user_ids()
        return await self.notify(admin_ids, type, entity_id, payload)
```

### Integration in MCP-Tools

```python
# In approve_review, nach State-Transition:
notifier = NotificationService(db)
await notifier.notify(
    user_ids=[task.assigned_to, task.epic.owner_id],
    type="task_done",
    entity_id=task.id,
    payload={"task_key": task.key, "title": task.title},
)

# In submit_guard_proposal, nach Lifecycle-Transition:
await notifier.notify_admins(
    type="guard_proposal",
    entity_id=guard.id,
    payload={"guard_id": str(guard.id), "title": guard.title},
)

# In propose_epic_restructure:
await notifier.notify_admins(
    type="restructure_proposal",
    entity_id=proposal.id,
    payload={"proposal_id": str(proposal.id), "type": proposal.restructure_type},
)
```

### SSE-Event-Format

```json
{
  "event": "notification",
  "data": {
    "id": "uuid",
    "type": "task_done",
    "payload": { "task_key": "TASK-88", "title": "Docker Setup" },
    "created_at": "2026-02-28T14:30:00Z"
  }
}
```

### Fehler-Behandlung

- Notification-Erstellung darf die Haupt-Transaktion **nicht** blockieren
- Bei SSE-Push-Fehler (Client disconnected): Log + ignorieren
- Notifications sind best-effort — kein Retry für SSE

### Wichtig
- Phase 5 speichert Notifications in der DB und pusht via SSE
- Phase 6 erweitert um einen dedizierten Notification-Service mit E-Mail/Webhook
- Nur Admins bekommen `guard_proposal` und `restructure_proposal`
- `task_done` geht an Assignee UND Owner (können identisch sein → Dedup greift)

### Verfügbare Tools
- `GET /api/notifications` — Alle Notifications des Users (paginiert)
- `PATCH /api/notifications/:id/read` — Als gelesen markieren
