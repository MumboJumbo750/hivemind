---
title: "AI-Provider-Settings: Per-Role-Konfiguration UI"
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

## Skill: AI-Provider-Settings UI

### Rolle
Du implementierst die Settings-Oberfläche für die AI-Provider-Konfiguration. Der Admin konfiguriert pro Agent-Rolle: Provider, Modell, Endpoint, API-Key, Token-Budget und RPM-Limit. Die UI unterstützt schrittweise Migration (eine Rolle automatisieren → dann weitere) und einen Test-Button pro Rolle.

### Konventionen
- View: `src/views/Settings/AIProvidersTab.vue`
- Composable: `src/composables/useAIProviders.ts`
- Nested Components in `src/components/settings/`
- Design Tokens für alle Farben/Spacing — keine Hardcodes
- API: `GET/PUT /api/settings/ai-providers` + `POST /api/settings/ai-providers/{role}/test`

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  ◈  SETTINGS — AI PROVIDERS                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ GLOBAL DEFAULT ─────────────────────────────────────────┐  │
│  │  Provider: [anthropic ▼]   Model: [claude-sonnet-4-20250514     ]  │
│  │  API-Key:  [••••••••••••••]  [🔑 Change]                │  │
│  │  RPM: [10]   TPM: [100000]                               │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Per-Role Overrides (überschreiben Global Default)              │
│  ─────────────────────────────────────────────────              │
│                                                                 │
│  ┌─ WORKER ─────────────────────────── [✓ Enabled] ────────┐  │
│  │  Provider: [ollama ▼]   Model: [llama3:70b           ]   │  │
│  │  Endpoint: [http://gpu1:11434                        ]   │  │
│  │  RPM: [10]   Token-Budget: [8000]                        │  │
│  │  Pool: [+ Add Endpoint]                                  │  │
│  │  [🧪 Test] → ✓ OK (1.2s, llama3:70b loaded)            │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ REVIEWER ──────────────────────── [✓ Enabled] ────────┐   │
│  │  Provider: [github_models ▼]   Model: [gpt-4o        ]  │  │
│  │  API-Key:  [••••••••••••••]  (GitHub PAT)                │  │
│  │  [🧪 Test] → ✓ OK (0.8s)                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ KARTOGRAPH ────────────────────── [  Disabled] ────────┐  │
│  │  → Verwendet Global Default (anthropic/claude-sonnet-4-20250514)  │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ... (Stratege, Architekt, Gaertner, Triage)                    │
│                                                                 │
│  [SPEICHERN]                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Provider-Auswahl

```typescript
interface ProviderOption {
  value: string
  label: string
  requiresApiKey: boolean
  requiresEndpoint: boolean
  supportsPool: boolean
}

const PROVIDERS: ProviderOption[] = [
  { value: 'anthropic', label: 'Anthropic (Claude)', requiresApiKey: true, requiresEndpoint: false, supportsPool: false },
  { value: 'openai', label: 'OpenAI (GPT)', requiresApiKey: true, requiresEndpoint: false, supportsPool: false },
  { value: 'google', label: 'Google (Gemini)', requiresApiKey: true, requiresEndpoint: false, supportsPool: false },
  { value: 'github_models', label: 'GitHub Models', requiresApiKey: true, requiresEndpoint: false, supportsPool: false },
  { value: 'ollama', label: 'Ollama (Self-Hosted)', requiresApiKey: false, requiresEndpoint: true, supportsPool: true },
  { value: 'custom', label: 'Custom (OpenAI-kompatibel)', requiresApiKey: true, requiresEndpoint: true, supportsPool: true },
]
```

### Endpoint-Pool-Editor

```vue
<template>
  <div v-if="provider.supportsPool" class="hv-pool-editor">
    <div class="hv-pool-editor__strategy">
      <label>Pool-Strategie:</label>
      <select v-model="config.pool_strategy">
        <option value="round_robin">Round Robin</option>
        <option value="weighted">Weighted (GPU-Stärke)</option>
        <option value="least_busy">Least Busy</option>
      </select>
    </div>

    <div v-for="(ep, i) in config.endpoints" :key="i" class="hv-pool-editor__endpoint">
      <input v-model="ep.url" placeholder="http://gpu1:11434" />
      <input v-model.number="ep.weight" type="number" min="1" max="10" />
      <input v-model="ep.name" placeholder="Name (optional)" />
      <span v-if="ep.healthy !== undefined" :class="ep.healthy ? 'healthy' : 'unhealthy'">
        {{ ep.healthy ? '●' : '○' }}
      </span>
      <button @click="removeEndpoint(i)">✕</button>
    </div>

    <button @click="addEndpoint">+ Endpoint hinzufügen</button>
  </div>
</template>
```

### Test-Button

```typescript
async function testProvider(role: string) {
  testing.value[role] = true
  try {
    const result = await api.post(`/api/settings/ai-providers/${role}/test`)
    testResults.value[role] = {
      success: result.data.ok,
      latency: result.data.latency_ms,
      model: result.data.model,
      error: result.data.error,
    }
  } finally {
    testing.value[role] = false
  }
}
```

### API-Key-Handling
- API-Key wird als Plaintext via HTTPS gesendet → Backend verschlüsselt sofort (AES-256-GCM)
- UI zeigt nur Masken (`••••••••••••••`) — nie den echten Key
- "Change"-Button öffnet Input; leerer Submit = Key beibehalten
- Validierung: Key-Format per Provider prüfen (Anthropic: `sk-ant-*`, OpenAI: `sk-*`, etc.)

### Schrittweise Migration
- Disabled-Rollen zeigen "Verwendet Global Default" an
- Enabled-Toggle pro Rolle → Override aktivieren
- Hybrid-Modus: manche Rollen auto, andere BYOAI
- Reihenfolge-Empfehlung im UI: "Empfohlen: Starte mit Worker, dann Reviewer"

### Wichtige Regeln
- API-Keys nie im Frontend cachen oder in localStorage speichern
- Alle Requests via HTTPS — TLS-Warnung bei HTTP-Endpunkten anzeigen
- Design Tokens für alle Farben: `--surface-*`, `--text-*`, `--accent-*`
- `Hv`-Prefix für alle Domain Components
