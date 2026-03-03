---
slug: skill-system
title: "Skill-System — Wiederverwendbare Instruktionen"
tags: [skills, gaertner, lifecycle, wiederverwendung]
linked_epics: [EPIC-PHASE-4, EPIC-PHASE-5]
---

# Skill-System — Wiederverwendbare Instruktionen

Skills sind versionierte, agent-agnostische Instruktions-Dokumente. Sie beschreiben **wie** bestimmte Aufgaben erledigt werden — wiederverwendbar über Tasks und Projekte hinweg.

## Format

Jeder Skill ist ein Markdown-Dokument mit YAML-Frontmatter:

```yaml
---
title: "FastAPI Endpoint erstellen"
skill_type: domain
lifecycle: active
tags: [backend, python, fastapi]
---

# FastAPI Endpoint

## Kontext
...

## Instruktionen
...
```

## Lifecycle

```
draft → pending_merge → active
                      → rejected
active → deprecated
```

- **draft:** Entwurf, noch nicht aktiv
- **pending_merge:** Vom Gaertner eingereicht, wartet auf Admin-Merge
- **active:** Aktiv und in Prompt-Generierung verwendbar
- **rejected:** Abgelehnt mit Begründung
- **deprecated:** Veraltet, nicht mehr in neuen Prompts

## Agenten-Rollen

| Agent | Aktion |
| --- | --- |
| **Gaertner** | Erstellt Skills aus abgeschlossenen Tasks (`propose_skill`) |
| **Kartograph** | Schlägt Skills vor basierend auf Code-Analyse (`propose_skill`) |
| **Admin** | Merged oder lehnt ab (`merge_skill` / `reject_skill`) |
| **Bibliothekar** | Wählt relevante Skills für Task-Kontext aus |
| **Architekt** | Verknüpft Skills mit Tasks (`link_skill`) |

## Federation

Skills mit `federation_scope = 'federated'` werden automatisch an alle bekannten Peers gepublished. Peers können federated Skills forken (`fork_federated_skill`) — keine direkte Bearbeitung möglich.

## Pinned Skills

Ein Task kann spezifische Skill-Versionen pinnen (`pinned_skills` JSONB-Array). Der Bibliothekar bevorzugt gepinnte Versionen über die jeweils aktuelle.
