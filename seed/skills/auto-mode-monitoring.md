---
title: "Auto-Mode Monitoring & AI-Review-Panel"
service_scope: ["frontend"]
stack: ["typescript", "vue3", "reka-ui", "sse"]
version_range: { "vue": ">=3.4", "typescript": ">=5.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-8"]
guards:
  - title: "Frontend Typecheck"
    command: "cd frontend && npm run typecheck"
  - title: "Frontend Build"
    command: "cd frontend && npm run build"
---

## Skill: Auto-Mode Monitoring & AI-Review-Panel

### Rolle
Du implementierst zwei zusammenhängende Frontend-Features für Phase 8:
1. **Prompt Station Auto-Modus** — Monitoring-Ansicht statt Prompt-Cards wenn ein Provider konfiguriert ist
2. **AI-Review-Panel** — Review-Empfehlung im Task-Detail mit 1-Click Approve/Reject und Grace-Period-Countdown

### Konventionen
- Prompt Station: `src/components/prompt/HvPromptStationAuto.vue`
- Review-Panel: `src/components/task/HvAIReviewPanel.vue`
- Composables: `src/composables/useAutoMode.ts`, `src/composables/useReviewRecommendation.ts`
- SSE-Events: `conductor_dispatched`, `conductor_completed`, `review_recommendation_created`
- Design Tokens — Sci-Fi Game HUD Aesthetic

### Prompt Station Auto-Modus

Im Auto-Modus verschwinden die Prompt-Cards. Stattdessen: Live-Monitoring.

```
┌─────────────────────────────────────────────────────────────────┐
│  ◈  PROMPT STATION — AUTO MODE                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ AKTIVE AGENTEN ────────────────────────────────────────┐   │
│  │  🟢 Worker    → TASK-142  "Implement auth middleware"    │   │
│  │     Provider: ollama/llama3  Tokens: 2.4k  Elapsed: 12s │   │
│  │  🟢 Gaertner  → TASK-139  "Destillation: API patterns"  │   │
│  │     Provider: anthropic/claude  Tokens: 1.1k  Elapsed: 5s│  │
│  │  ⏸ Reviewer  → (queued: TASK-140)                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ TOKEN-VERBRAUCH (24h) ─────────────────────────────────┐   │
│  │  Worker:      12.4k  ████████████░░░  (Budget: 20k)     │   │
│  │  Reviewer:     3.2k  ████░░░░░░░░░░░  (Budget: 10k)     │   │
│  │  Kartograph:   0.8k  █░░░░░░░░░░░░░░  (Budget: 10k)     │   │
│  │  Gesamt:      16.4k / 50k RPM: 8/10                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ LETZTE DISPATCHES ─────────────────────────────────────┐   │
│  │  14:32  ✓ Worker    TASK-141  done  (3.2k tokens, 45s)  │   │
│  │  14:30  ✓ Reviewer  TASK-139  approved (92% confidence)  │   │
│  │  14:28  ✗ Worker    TASK-140  failed (rate limited)      │   │
│  │  14:25  ✓ Gaertner  TASK-138  done  (1.8k tokens, 12s)  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  [🔧 MANUELL EINGREIFEN]  ← Schaltet zurück auf Prompt-Cards  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### "Manuell eingreifen"-Button

```typescript
async function switchToManual() {
  // Deaktiviert Auto-Modus für ALLE Rollen sofort
  // Laufende Dispatches werden zu Ende geführt
  // Prompt Station schaltet zurück auf Card-Ansicht
  await api.post('/api/settings/auto-mode/disable')
  autoMode.value = false
}
```

### AI-Review-Panel (Task-Detail)

Drei Modi je nach Governance-Level:

**`governance.review = 'assisted'`:**
```
┌──────────────────────────────────────────────┐
│  AI-REVIEW ✓  Empfehlung: APPROVE            │
│  Confidence: 92%  ████████████████████░░      │
│  "DoD erfüllt, alle Guards passed."           │
│                                               │
│  Checklist:                                   │
│    ✓ Unit Tests ≥ 80%  (87% coverage)         │
│    ✓ API-Docs aktualisiert                    │
│    ✓ Keine Security-Issues erkannt            │
│                                               │
│  [✓ APPROVE]  [✗ REJECT]  [DETAILS ▤]       │
└──────────────────────────────────────────────┘
```

**`governance.review = 'auto'` (Grace Period aktiv):**
```
┌──────────────────────────────────────────────┐
│  AI-REVIEW ✓  AUTO-APPROVED                  │
│  Confidence: 94%                              │
│                                               │
│  ⏱ Grace Period: 24:18 verbleibend           │
│  Auto-Approve um 15:02 wenn kein Einspruch    │
│                                               │
│  [🛑 EINGREIFEN — Veto]  [DETAILS ▤]        │
└──────────────────────────────────────────────┘
```

**`governance.review = 'auto'` (Reject-Empfehlung → Fallback auf Assisted):**
```
┌──────────────────────────────────────────────┐
│  AI-REVIEW ⚠  Empfehlung: REJECT             │
│  Confidence: 95%                              │
│  "Hardcoded API-Key in src/config.py:42"     │
│                                               │
│  ⚠ Auto-Reject nicht möglich.                │
│  Bitte manuell entscheiden.                   │
│                                               │
│  [✓ TROTZDEM APPROVE]  [✗ REJECT]            │
└──────────────────────────────────────────────┘
```

### Grace-Period-Countdown

```vue
<script setup lang="ts">
import { useIntervalFn } from '@vueuse/core'

const props = defineProps<{ autoApproveAt: string }>()
const remaining = ref('')

useIntervalFn(() => {
  const diff = new Date(props.autoApproveAt).getTime() - Date.now()
  if (diff <= 0) {
    remaining.value = 'Auto-Approved'
    return
  }
  const mins = Math.floor(diff / 60000)
  const secs = Math.floor((diff % 60000) / 1000)
  remaining.value = `${mins}:${secs.toString().padStart(2, '0')}`
}, 1000)
</script>
```

### Veto-Action

```typescript
async function vetoAutoReview(taskKey: string) {
  await api.post(`/api/tasks/${taskKey}/review/veto`)
  // Panel wechselt zu Assisted-Modus (manuelles Approve/Reject)
}
```

### SSE-Events
- `conductor_dispatched` → Aktiven Agenten in Monitoring hinzufügen
- `conductor_completed` → Agent aus aktiver Liste entfernen, in History verschieben
- `review_recommendation_created` → AI-Review-Panel anzeigen/aktualisieren
- `review_auto_approved` → Grace-Period-Countdown starten
- `review_vetoed` → Panel auf manuelle Entscheidung umschalten

### Wichtige Regeln
- "Manuell eingreifen" ist **jederzeit** verfügbar — Auto-Modus kann sofort verlassen werden
- Auto-Reject gibt es **nicht** — Reject-Empfehlung → immer Fallback auf Assisted
- Grace-Period-Countdown aktualisiert sich jede Sekunde (kein Polling, lokaler Timer)
- Token-Verbrauch-Anzeige per SSE live aktualisiert
- Design: Sci-Fi HUD — dunkle Palette, Monospace für Zahlen
