---
title: "Governance-Settings UI: Autonomie-Stufen konfigurieren"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "reka-ui"]
version_range: { "vue": ">=3.4", "typescript": ">=5.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-8"]
guards:
  - title: "Frontend Typecheck"
    command: "cd frontend && npm run typecheck"
  - title: "Frontend Build"
    command: "cd frontend && npm run build"
---

## Skill: Governance-Settings UI

### Rolle
Du implementierst den Governance-Tab in den Settings. Der Admin konfiguriert pro Entscheidungstyp (7 Typen) den Automatisierungsgrad (manual / assisted / auto). Die UI zeigt Safeguard-Informationen und eine Autonomie-Spektrum-Visualisierung.

### Konventionen
- View: `src/views/Settings/GovernanceTab.vue`
- Composable: `src/composables/useGovernance.ts`
- API: `GET/PUT /api/settings/governance`
- Design Tokens — keine Hardcodes
- Admin-only: nicht sichtbar für `developer`-Rolle

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ◈  SETTINGS — GOVERNANCE                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ AUTONOMIE-SPEKTRUM ────────────────────────────────────┐   │
│  │  ██████████░░░░░░░░░░  3/7 automated                    │   │
│  │  [MANUAL ████] [ASSISTED ██] [AUTO ████]                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Autonomie-Level pro Entscheidungstyp                           │
│  ─────────────────────────────────────                          │
│                                                                 │
│  Review             ○ Manual   ◉ Assisted   ○ Auto             │
│    ⓘ Assisted: AI pre-reviewed, Owner 1-Click Approve           │
│    ⚙ Auto-Threshold: [0.90]  Grace Period: [30] Min            │
│                                                                 │
│  Epic-Proposals     ◉ Manual   ○ Assisted   ○ Auto             │
│    ⓘ Manual: Admin reviewed alle Proposals in Triage Station    │
│                                                                 │
│  Epic-Scoping       ○ Manual   ○ Assisted   ◉ Auto             │
│    ⓘ Auto: Scope basierend auf Kartograph-Coverage (≥80%)      │
│    ⚠ Safeguard: Fallback auf Assisted bei Coverage < 80%       │
│                                                                 │
│  Skill-Merge        ○ Manual   ○ Assisted   ◉ Auto             │
│    ⓘ Auto: Auto-Merge nach ≥ [3] erfolgreichen Einsätzen      │
│    ⚠ Safeguard: Fallback bei erstem Einsatz oder Duplikat      │
│                                                                 │
│  Guard-Merge        ○ Manual   ○ Assisted   ◉ Auto             │
│    ⓘ Auto: Deterministisch — Command auf Allowlist + valide    │
│                                                                 │
│  Decision Requests  ◉ Manual   ○ Assisted   ○ Auto             │
│    ⓘ Manual: Owner entscheidet bei blockierten Tasks           │
│                                                                 │
│  Escalation         ○ Manual   ◉ Assisted   ○ Auto             │
│    ⓘ Assisted: AI schlägt Resolution vor, Admin bestätigt      │
│                                                                 │
│  ╔═══════════════════════════════════════════════════════╗      │
│  ║ ⚠  Auto = AI entscheidet autonom.                    ║      │
│  ║    Owner wird notifiziert + kann widersprechen.       ║      │
│  ║    Grace Period: konfigurierbar pro Typ               ║      │
│  ║    Auto-Reject ist NICHT möglich.                     ║      │
│  ╚═══════════════════════════════════════════════════════╝      │
│                                                                 │
│  [SPEICHERN]                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Autonomie-Spektrum-Visualisierung

```vue
<script setup lang="ts">
const levels = computed(() => {
  const counts = { manual: 0, assisted: 0, auto: 0 }
  for (const level of Object.values(governance.value)) {
    counts[level as keyof typeof counts]++
  }
  return counts
})

const automationPercent = computed(() =>
  Math.round(((levels.value.assisted + levels.value.auto) / 7) * 100)
)
</script>

<template>
  <div class="hv-autonomy-spectrum">
    <div class="hv-autonomy-spectrum__bar">
      <div
        class="hv-autonomy-spectrum__segment hv-autonomy-spectrum__segment--manual"
        :style="{ width: `${(levels.manual / 7) * 100}%` }"
      />
      <div
        class="hv-autonomy-spectrum__segment hv-autonomy-spectrum__segment--assisted"
        :style="{ width: `${(levels.assisted / 7) * 100}%` }"
      />
      <div
        class="hv-autonomy-spectrum__segment hv-autonomy-spectrum__segment--auto"
        :style="{ width: `${(levels.auto / 7) * 100}%` }"
      />
    </div>
    <span class="hv-autonomy-spectrum__label">
      {{ automationPercent }}% automatisiert
    </span>
  </div>
</template>

<style scoped>
.hv-autonomy-spectrum__segment--manual { background: var(--color-text-muted); }
.hv-autonomy-spectrum__segment--assisted { background: var(--color-accent-primary); }
.hv-autonomy-spectrum__segment--auto { background: var(--color-success); }
</style>
```

### Safeguard-Anzeige

Jeder Typ im `auto`-Modus zeigt seine Safeguard-Bedingung:

```typescript
const SAFEGUARDS: Record<string, string> = {
  review: 'Fallback auf Assisted bei Confidence < Threshold oder Reject-Empfehlung',
  epic_proposals: 'Fallback bei Duplikat oder fehlender Rationale',
  epic_scoping: 'Fallback bei Kartograph-Coverage < 80%',
  skill_merge: 'Fallback bei erstem Einsatz oder Duplikat-Warnung',
  guard_merge: 'Fallback wenn Command nicht auf Allowlist',
  decisions: 'Fallback bei > 2 Optionen oder unklarer Präferenz',
  escalations: 'Fallback bei erstmaliger Eskalation oder unbekanntem Pattern',
}
```

### Wichtige Regeln
- Kein globaler "Full Auto"-Button — jeder Typ einzeln konfigurierbar
- Auto-Konfiguration (Threshold, Grace Period) nur sichtbar wenn Level = `auto`
- Safeguard-Info immer sichtbar bei `auto` (User muss Einschränkungen kennen)
- Admin-only — developer-Rolle sieht den Tab nicht
- Änderungen erzeugen Audit-Log-Eintrag
