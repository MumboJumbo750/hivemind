---
slug: "state-machine-guide"
title: "State Machine — Task & Epic Lifecycle"
tags: ["state-machine", "tasks", "epics", "workflow"]
linked_epics: ["EPIC-PHASE-1A", "EPIC-PHASE-2"]
---

# State Machine — Task & Epic Lifecycle

## Task-States

```
incoming → scoped → ready → in_progress → in_review → done
                                 │              │
                                 ↓              ↓
                              blocked       qa_failed → in_progress (Retry)
                                 │
                                 ↓
                             escalated (3x qa_failed ODER Decision-SLA > 72h)
```

| State | Bedeutung | Nächster Schritt |
| --- | --- | --- |
| `incoming` | Task eingegangen, noch nicht gescoped | Architekt scopt |
| `scoped` | Scope definiert, Context Boundary gesetzt | Architekt weist zu |
| `ready` | Zugewiesen, wartet auf Worker | Worker nimmt an |
| `in_progress` | Worker arbeitet | Worker liefert Ergebnis |
| `in_review` | Ergebnis liegt vor, Review läuft | Owner genehmigt/lehnt ab |
| `done` | Abgeschlossen | Gaertner destilliert Skills |
| `blocked` | Decision Request offen | Owner/Admin löst auf |
| `qa_failed` | Review abgelehnt | Worker überarbeitet |
| `escalated` | 3x qa_failed oder SLA-Überschreitung | Admin greift ein |
| `cancelled` | Abgebrochen | — |

> **Wichtig:** `decompose_epic` erstellt Tasks immer als `incoming`.
> Der Architekt muss Tasks manuell **zwei Schritte** transitionieren:
> `incoming → scoped → ready` (direktes `incoming → ready` ist nicht erlaubt).
> `scoped → ready` erfordert, dass `assigned_to` gesetzt ist (sonst 422).

## Epic-States

```
incoming → scoped → in_progress → done
```

- **Auto-Transition `scoped → in_progress`:** Sobald der erste Task `in_progress` geht
- **Auto-Transition `in_progress → done`:** Sobald alle Tasks `done` oder `cancelled` sind

## Review-Gate

**Fundamentale Regel:** Kein Task darf direkt von `in_progress` nach `done` wechseln. Der Weg geht immer über `in_review`. Das gilt auch im Solo-Modus — als Arbeitsdisziplin.
