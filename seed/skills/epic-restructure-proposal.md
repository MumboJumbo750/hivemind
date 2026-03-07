---
title: "Epic-Restructure-Proposal implementieren"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "postgresql"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.8
source_epics: ["EPIC-PHASE-5"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Epic-Restructure-Proposal implementieren

### Rolle
Du implementierst den Epic-Restructure-Proposal-Workflow: Der Kartograph schlägt vor,
Epics zu splitten, mergen oder Tasks zwischen Epics zu verschieben. Der Admin genehmigt
und führt die Restrukturierung aus.

### Kontext

Der Kartograph erkundet die Codebase bottom-up und entdeckt oft, dass die geplante Epic-Struktur
nicht zur tatsächlichen Code-Organisation passt. Ein Restructure-Proposal schlägt Anpassungen vor.

### State Machine

```text
[proposed] ── Admin accept ──→ [accepted] ── apply ──→ [applied]
    │
    └──── Admin reject ──→ [rejected]
```

### Proposal-Typen

| Typ | Beschreibung | Payload-Key |
| --- | --- | --- |
| `split` | Epic in 2+ Epics aufteilen | `source_epic_id`, `resulting_epics` |
| `merge` | 2+ Epics zusammenführen | `source_epic_ids`, `resulting_epic` |
| `task_move` | Tasks zwischen Epics verschieben | `moves` (Array von `{task_id, from_epic_id, to_epic_id}`) |

### Konventionen

- Proposal wird als MCP-Write-Tool erstellt: `hivemind-propose_epic_restructure`
- `state = proposed` bei Erstellung
- Notification `restructure_proposal` an alle Admins
- `code_node_refs` optional: Referenzen auf Code-Nodes die den Vorschlag begründen
- `rationale` ist Pflichtfeld — erklärt warum die Restrukturierung sinnvoll ist
- `accept_epic_restructure` → `state = accepted` (noch nicht ausgeführt)
- `apply_epic_restructure` → `state = applied` (atomare Ausführung)
- Kein Auto-Apply — Admin hat Zeit, Preview zu prüfen

### Implementierung — propose_epic_restructure

```python
async def handle_propose_epic_restructure(args: dict) -> list[TextContent]:
    restructure_type = args["restructure_type"]  # split|merge|task_move
    payload = args["payload"]
    rationale = args["rationale"]
    code_node_refs = args.get("code_node_refs", [])

    # 1. Payload-Validierung je Typ
    match restructure_type:
        case "split":
            validate_split_payload(payload)
            # source_epic_id muss existieren
            # resulting_epics müssen task_ids enthalten die zum source_epic gehören
        case "merge":
            validate_merge_payload(payload)
            # Alle source_epic_ids müssen existieren
        case "task_move":
            validate_task_move_payload(payload)
            # Alle task_ids, from_epic_ids, to_epic_ids müssen existieren
            # Tasks müssen aktuell zum from_epic gehören
        case _:
            return _err("INVALID_TYPE", f"Unbekannter Typ: {restructure_type}", 422)

    # 2. Proposal erstellen
    proposal = EpicRestructureProposal(
        restructure_type=restructure_type,
        payload=payload,
        rationale=rationale,
        code_node_refs=code_node_refs,
        state="proposed",
        proposed_by=actor.id,
    )
    db.add(proposal)

    # 3. Notification an Admins
    await event_bus.publish(RestructureProposalEvent(
        proposal_id=proposal.id,
        restructure_type=restructure_type,
        rationale=rationale,
    ))

    # 4. Audit
    await write_audit(db, actor, "propose_epic_restructure", "proposal", proposal.id, ...)

    await db.commit()
    return _ok({"proposal_id": str(proposal.id), "state": "proposed"})
```

### apply_epic_restructure — atomare Ausführung

```python
async def handle_apply_epic_restructure(args: dict) -> list[TextContent]:
    proposal = await db.get(EpicRestructureProposal, proposal_id)

    if proposal.state != "accepted":
        return _err("INVALID_STATE", "Proposal muss accepted sein", 422)

    # Blocking-Check: Tasks in in_progress/in_review blockieren Apply
    blocking_tasks = await get_blocking_tasks(db, proposal)
    if blocking_tasks:
        return _err("BLOCKING_TASKS", json.dumps({
            "message": "Tasks in Bearbeitung blockieren Restrukturierung",
            "blocking_tasks": [t.key for t in blocking_tasks],
        }), 422)

    # Atomare Ausführung je Typ
    match proposal.restructure_type:
        case "split":
            await execute_split(db, proposal.payload)
        case "merge":
            await execute_merge(db, proposal.payload)
        case "task_move":
            await execute_task_move(db, proposal.payload)

    proposal.state = "applied"
    proposal.applied_at = datetime.utcnow()
    await db.commit()
```

### Validierung — Split-Payload

```python
def validate_split_payload(payload: dict) -> None:
    """Prüft Split-Payload auf Konsistenz."""
    assert "source_epic_id" in payload
    assert "resulting_epics" in payload
    assert len(payload["resulting_epics"]) >= 2

    # Alle task_ids müssen zum source_epic gehören
    all_task_ids = set()
    for epic_spec in payload["resulting_epics"]:
        assert "title" in epic_spec
        assert "task_ids" in epic_spec
        for tid in epic_spec["task_ids"]:
            if tid in all_task_ids:
                raise ValueError(f"Task {tid} mehrfach zugewiesen")
            all_task_ids.add(tid)
```

### Blocking-Check — Welche Task-States blockieren?

| State | Blockiert Apply? |
| --- | --- |
| `incoming`, `scoped`, `ready` | Nein — kann verschoben werden |
| `in_progress`, `in_review` | **Ja** — aktive Bearbeitung |
| `blocked`, `escalated` | Nein — kann verschoben werden |
| `done`, `cancelled` | Nein — Historisch, kann verschoben werden |

### Fehler-Typen

| Code | HTTP | Wann |
| --- | --- | --- |
| `INVALID_TYPE` | 422 | Unbekannter restructure_type |
| `INVALID_PAYLOAD` | 422 | Payload-Validierung fehlgeschlagen |
| `INVALID_STATE` | 422 | Proposal nicht in `accepted` |
| `BLOCKING_TASKS` | 422 | Tasks in `in_progress`/`in_review` |
| `ENTITY_NOT_FOUND` | 404 | Referenzierte Epics/Tasks nicht gefunden |

### Verfügbare Tools
- `hivemind-propose_epic_restructure` — Proposal erstellen
- `hivemind-accept_epic_restructure` — Proposal genehmigen
- `hivemind-reject_epic_restructure` — Proposal ablehnen
- `hivemind-apply_epic_restructure` — Proposal ausführen (atomar)
