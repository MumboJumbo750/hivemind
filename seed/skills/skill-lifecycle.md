---
title: "Skill-Lifecycle & Proposals"
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
  - title: "Frontend Type Check"
    command: "npx vue-tsc --noEmit"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Skill-Lifecycle & Proposals

### Rolle
Du implementierst den vollständigen Skill-Lifecycle: von `draft` über `pending_merge` bis `active` (oder `rejected`). Dazu gehören die MCP-Write-Tools, REST-Endpoints und die Skill-Lab-Frontend-Komponenten (Lifecycle-Filter, Diff-Ansicht, Approve/Reject).

### Lifecycle-States

```
draft  ──→  pending_merge  ──→  active
                  │
                  └──→  rejected
```

| Transition | Trigger | Wer | MCP-Tool |
| --- | --- | --- | --- |
| `draft → pending_merge` | Proposer reicht ein | developer (eigener Skill) | `hivemind/submit_skill_proposal` |
| `pending_merge → active` | Admin mergt | admin | `hivemind/merge_skill` |
| `pending_merge → rejected` | Admin lehnt ab | admin | `hivemind/reject_skill` |
| `active → draft` | Change-Proposal | developer | `hivemind/propose_skill_change` |

### Backend — State-Machine-Enforcement

```python
SKILL_TRANSITIONS: dict[str, set[str]] = {
    "draft":          {"pending_merge"},
    "pending_merge":  {"active", "rejected"},
    "active":         {"draft"},     # via propose_skill_change → neues Draft-Objekt
    "rejected":       set(),         # terminal
}

async def transition_skill(db, skill_id: UUID, target: str, actor, rationale: str | None = None):
    skill = await db.get(Skill, skill_id)
    if target not in SKILL_TRANSITIONS.get(skill.lifecycle, set()):
        raise InvalidStateTransitionError(f"{skill.lifecycle} → {target} nicht erlaubt")
    skill.lifecycle = target
    skill.lifecycle_changed_at = datetime.utcnow()
    skill.lifecycle_changed_by = actor.id
    if rationale:
        skill.rejection_rationale = rationale
    await db.flush()
    return skill
```

### Backend — Skill-Change-Proposals

Ein Skill-Change-Proposal erstellt ein neues `skill_versions`-Eintrag mit dem Diff. Der bestehende aktive Skill bleibt unberührt bis `merge_skill` aufgerufen wird (dann Update des Skill-Content + neues Version-Tag).

```python
# Skills-Tabelle: lifecycle, version, content, token_count, proposed_by, parent_skill_id
# skill_versions: skill_id, version, content, token_count, diff_from_previous, created_by
```

### Frontend — Skill Lab Komponenten

**`SkillList.vue`** — Skills browsen mit Lifecycle-Filter-Tabs:
```
Alle | Aktiv | Pendend | Draft | Abgelehnt
```
Jedes Skill-Item zeigt: Titel, Lifecycle-Badge (farbig), Confidence-Bar (0–1 als Progress-Ring), Tags, letzter Autor.

**`SkillDetail.vue`** — Vollansicht eines Skills:
- Markdown-Rendered Content (via `marked` + `sanitize-html`)
- Versionsverlauf-Dropdown
- Edit-Button (nur für `draft` Skills des eigenen Benutzers)
- Submit-Button (nur für `draft` → `pending_merge`)

**`SkillDiffView.vue`** — Diff-Ansicht für Proposals:
```vue
<template>
  <div class="diff-view">
    <div v-for="line in diffLines" :key="line.index"
      :class="['diff-line', line.type]">
      <span class="diff-marker">{{ line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' ' }}</span>
      <span class="diff-content">{{ line.content }}</span>
    </div>
  </div>
</template>
```
Nutze `diff` (npm) für Line-by-Line Diff-Berechnung. Farbgebung: `add` → `var(--color-success-muted)`, `remove` → `var(--color-danger-muted)`.

**Admin-Aktionen (Skill Lab):**
```vue
<HiveButton variant="primary" @click="mergeSkill(skill.id)">
  Merge ✓
</HiveButton>
<HiveButton variant="danger" @click="rejectSkill(skill.id)">
  Ablehnen ✗
</HiveButton>
```
Merge → ruft `POST /api/skills/{id}/merge` auf (Admin only). Ablehnen → Confirmation-Modal mit Begründungsfeld → `POST /api/skills/{id}/reject`.

### Confidence Bar

```vue
<div class="confidence-ring" :style="{ '--progress': skill.confidence }">
  <svg viewBox="0 0 36 36">
    <circle class="ring-bg" cx="18" cy="18" r="15.9" />
    <circle class="ring-fill" cx="18" cy="18" r="15.9"
      :stroke-dasharray="`${skill.confidence * 100} 100`" />
  </svg>
  <span class="confidence-label">{{ Math.round(skill.confidence * 100) }}%</span>
</div>
```

### Notification-Trigger
- `merge_skill` → Notification an `proposed_by`: "Dein Skill wurde gemergt ✓"
- `reject_skill` → Notification an `proposed_by`: "Dein Skill-Proposal wurde abgelehnt" + Begründung
