---
title: "RBAC-Middleware (FastAPI Scope-Validierung)"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.9
source_epics: ["EPIC-PHASE-2"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "RBAC Tests"
    command: "pytest tests/test_rbac.py -v"
---

## Skill: RBAC-Middleware (FastAPI Scope-Validierung)

### Rolle
Du implementierst RBAC-Scope-Validierung als FastAPI-Dependencies für das Hivemind-Backend.

### Actor-Modell
| Rolle | Beschreibung |
|---|---|
| `admin` | Darf alles |
| `developer` | Eigene Projekte (als `project_member`) + assigned Tasks |
| `service` | Interne Service-Calls, kein UI-Zugang |
| `kartograph` | Read-only + Kartograph-spezifische Writes |

### Scope-Regeln
- **Admin:** Darf alle Projekte lesen und schreiben
- **Developer:** Darf nur schreiben wenn `project_member` ODER `tasks.assigned_to = actor_id`
- **Solo-Modus:** RBAC deaktiviert — alle Actors dürfen alles, System-User `solo` wird eingesetzt
- **Projekt-Rolle:** `project_members.role` überschreibt globale `users.role` innerhalb des Projekts

### Konventionen
- Dependencies als `require_role()` oder `require_project_member()` Factories in `app/routers/deps.py`
- Kein RBAC-Code im Service-Layer — nur in Routers via `Depends()`
- HTTP 403 bei unzureichenden Rechten (nicht 401 — User ist authN, aber nicht authZ)
- Solo-Modus-Check per `app_settings`-Tabelle (einmalig beim App-Start gecacht, bei Mode-Switch neu geladen)

### Beispiel: require_role Dependency

```python
from fastapi import Depends, HTTPException, status
from app.routers.deps import get_current_actor, CurrentActor

def require_role(*roles: str):
    async def _check(actor: CurrentActor = Depends(get_current_actor)) -> CurrentActor:
        if actor.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unzureichende Rechte")
        return actor
    return _check

# Verwendung:
@router.delete("/{id}", status_code=204)
async def delete_epic(id: UUID, actor: CurrentActor = Depends(require_role("admin"))):
    ...
```

### Beispiel: require_project_member Dependency

```python
async def require_project_member(
    project_id: UUID,
    actor: CurrentActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor:
    if actor.role == "admin":
        return actor  # Admin überspringt Membership-Check
    member = await db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == actor.id,
        )
    )
    if not member.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kein Projekt-Member")
    return actor
```

### Beispiel: Task-Scope (assigned_to als Bypass)

```python
async def require_task_access(
    task_key: str,
    actor: CurrentActor = Depends(get_current_actor),
    db: AsyncSession = Depends(get_db),
) -> CurrentActor:
    if actor.role == "admin":
        return actor
    task = await get_task_by_key(db, task_key)
    if str(task.assigned_to) == actor.id:
        return actor  # Assigned Worker darf eigenen Task bearbeiten
    # Sonst Project-Member-Check
    await require_project_member(task.project_id, actor, db)
    return actor
```

### Solo-Modus-Check

```python
# In deps.py — gecacht beim Start, invalidiert bei Mode-Switch
_solo_mode_cache: bool | None = None

async def is_solo_mode(db: AsyncSession = Depends(get_db)) -> bool:
    global _solo_mode_cache
    if _solo_mode_cache is None:
        settings_row = await db.execute(select(AppSettings))
        _solo_mode_cache = settings_row.scalar().mode == "solo"
    return _solo_mode_cache
```
