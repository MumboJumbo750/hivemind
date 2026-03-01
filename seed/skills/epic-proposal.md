---
title: "Epic-Proposal Workflow"
service_scope: ["backend", "frontend"]
stack: ["python", "fastapi", "sqlalchemy", "vue", "typescript"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100", "vue": ">=3.4" }
confidence: 0.85
source_epics: ["EPIC-PHASE-4"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Epic-Proposal Workflow

### Rolle
Du implementierst den Epic-Proposal-Workflow: Stratege schlägt Epics via MCP vor, Triage/Admin akzeptiert oder lehnt ab. Bei Akzeptanz entsteht ein echtes Epic mit `state='incoming'`.

### State Machine

```
proposed ──→ accepted  ──→  (resulting_epic: incoming)
    │
    └──→ rejected
```

### Datenmodell — `epic_proposals`-Tabelle

```sql
CREATE TABLE epic_proposals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id),
    proposed_by     UUID NOT NULL REFERENCES users(id),
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    rationale       TEXT,
    state           TEXT NOT NULL DEFAULT 'proposed',  -- proposed | accepted | rejected
    depends_on      UUID[],                             -- andere Proposal-IDs
    resulting_epic_id UUID REFERENCES epics(id),        -- gesetzt nach accept
    rejection_reason  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    version         INT NOT NULL DEFAULT 1
);
```

### MCP-Tools

```python
# Stratege: neues Proposal erstellen
hivemind/propose_epic {
  "project_id": "uuid",
  "title": "...",
  "description": "...",
  "rationale": "Warum dieses Epic jetzt?",
  "depends_on": ["other-proposal-uuid"]   # optional
}

# Stratege: Proposal nachbessern (nur im state 'proposed')
hivemind/update_epic_proposal {
  "proposal_id": "uuid",
  "title": "...",        # optional
  "description": "...", # optional
  "version": 2           # Optimistic Lock
}

# Triage/Admin: akzeptieren → erstellt Epic (state=incoming)
hivemind/accept_epic_proposal {
  "proposal_id": "uuid"
}
# Setzt resulting_epic_id, Proposal-State → accepted
# Erzeugt Epic mit state='incoming' und einer 'epic_proposal_source'-Relation

# Triage/Admin: ablehnen
hivemind/reject_epic_proposal {
  "proposal_id": "uuid",
  "reason": "Scope zu groß, bitte in 2 Proposals aufteilen"
}
# Benachrichtigt proposed_by
# Warnt abhängige Proposals deren depends_on dieses Proposal enthält
```

### Abhängigkeits-Warnung

Wenn ein Proposal abgelehnt wird und andere Proposals es in `depends_on` referenzieren, werden diese Proposals mit einem Warning-Flag versehen:

```python
async def reject_proposal(db, proposal_id, reason, actor):
    proposal = await get_proposal(db, proposal_id)
    require_permission(actor, "manage_proposals")  # admin or triage

    proposal.state = "rejected"
    proposal.rejection_reason = reason

    # Abhängige Proposals warnen
    dependents = await db.execute(
        select(EpicProposal).where(
            EpicProposal.state == "proposed",
            EpicProposal.depends_on.contains([proposal_id])
        )
    )
    for dep in dependents.scalars():
        await event_bus.publish(ProposalDependencyRejectedEvent(
            proposal_id=dep.id,
            rejected_dependency_id=proposal_id
        ))
    # ...
```

### REST-Endpoints

```
GET    /api/epic-proposals?project_id=&state=         # list (triage/admin)
POST   /api/epic-proposals                             # propose_epic (developer+)
PATCH  /api/epic-proposals/{id}                        # update_epic_proposal  
POST   /api/epic-proposals/{id}/accept                 # accept (triage/admin)
POST   /api/epic-proposals/{id}/reject                 # reject (triage/admin)
```

### Frontend — Triage Station: [EPIC PROPOSAL]-Kategorie

In der Triage Station einen neuen Tab/Filter `EPIC PROPOSALS` hinzufügen:
- Liste der Proposals mit State-Badge (`proposed` → gelb, `accepted` → grün, `rejected` → rot)
- Proposal-Detail-Panel: Titel, Beschreibung, Rationale, Proposer, depends_on-Kette
- Admin-Aktionen: `[AKZEPTIEREN]` → Bestätigung → `accept_epic_proposal`
- Admin-Aktionen: `[ABLEHNEN]` → Modal mit Begründungsfeld → `reject_epic_proposal`
- Abhängigkeits-Warnung: wenn `depends_on`-Proposal rejected → rotes Warning-Banner

### Notification-Trigger
- `accept_epic_proposal` → Notification an `proposed_by`: "Epic Proposal akzeptiert — EPIC-XX erstellt"
- `reject_epic_proposal` → Notification an `proposed_by`: "Epic Proposal abgelehnt: {reason}"
- Abhängigkeits-Warnung → Notification an Proposer des abhängigen Proposals

### RBAC-Übersicht

| Operation | Permission | Wer |
| --- | --- | --- |
| `propose_epic` | `write_epics` | developer, admin |
| `update_epic_proposal` | `write_epics` (eigene Proposals) | proposer, admin |
| `accept_epic_proposal` | `manage_proposals` | triage, admin |
| `reject_epic_proposal` | `manage_proposals` | triage, admin |
