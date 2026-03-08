# Runbook: E2E Agent Loop Tests

Tests für den vollständigen agentic Orchestrierungspfad: `agentic_dispatch` → `ConductorService` → Tool-Ausführung → Lern-Artefakt.

## Lokale Ausführung

```bash
# Nur E2E-Orchestrierungstests
make shell-be
pytest tests/test_e2e_orchestration.py -v

# Kombiniert mit verwandten Test-Modulen
pytest tests/test_e2e_orchestration.py tests/test_conductor_workflow.py tests/test_agentic_dispatch.py -v

# Einzelnen Test isolieren
pytest tests/test_e2e_orchestration.py -k "test_full_worker_and_reviewer_loop" -v

# Alle Backend-Tests (CI-äquivalent)
make test
```

## Test-Matrix

| Test | Was wird verifiziert |
|------|----------------------|
| `test_scripted_provider_*` | `ScriptedAIProvider` liefert Antworten in der richtigen Reihenfolge |
| `test_agentic_dispatch_single_turn_no_tools` | Single-Turn ohne Tool-Calls funktioniert |
| `test_agentic_dispatch_native_tool_calls` | XML-Text-Tool-Calls werden geparsed und ausgeführt |
| `test_full_worker_and_reviewer_loop_via_conductor` | Worker → Submit → Reviewer → Approve (voller Conductor-Loop) |
| `test_qa_failed_worker_retry_creates_learning_artifact` | QA-Failed → Worker-Retry funktioniert |
| `test_triage_dispatch_routes_event_with_tool_calls` | Triage-Rolle führt `hivemind-route_event` aus |
| `test_stratege_epic_proposal_path` | Stratege-Rolle führt `hivemind-propose_epic` aus |
| `test_provider_error_captured_in_result` | Provider-Fehler landet in `result.error`, kein Exception-Crash |
| `test_max_iterations_cap_stops_runaway_agent` | `max_iterations` stoppt endlosen Tool-Call-Loop |
| `test_conductor_skips_when_cooldown_active` | Cooldown-Gate blockiert Dispatch (`status="cooldown_skipped"`) |
| `test_conductor_local_fallback_on_agentic_error` | Provider-Exception → `byoai`/`failed`-Status |
| `test_default_fallback_chain_*` | `_default_fallback_chain()` gibt korrekte Ketten zurück |
| `test_learning_loop_injection_blocked_in_worker_output` | Prompt-Injection im Worker-Output → Learning blockiert |
| `test_learning_loop_*` | Quality-Gate: Confidence-Schwellen und Review-Pfade |
| `test_agentic_dispatch_with_learning_creation` | Tool-Ausführung erzeugt Learning-Signal |
| `test_role_tools_correctly_filtered_for_all_roles` | Rollenfilterung gibt korrekte Tool-Subsets zurück |
| `test_parse_text_tool_calls_*` | XML-Tool-Call-Parser: korrekt, mehrfach, leer, malformed |
| `test_system_prompt_*` | System-Prompt enthält Rolle, Task-Key und Tool-Docs |
| `test_oversized_prompt_is_truncated_before_dispatch` | Überlanger Prompt wird auf Budget gekürzt |

## Architektur der Test-Stubs

### ScriptedAIProvider

Deterministischer AI-Provider für Tests. Gibt eine vordefinierte Sequenz von `AIResponse`-Objekten zurück.

```python
provider = ScriptedAIProvider([
    AIResponse(
        content='<tool_call>{"name": "hivemind-get_task", "arguments": {"task_key": "TASK-1"}}</tool_call>',
        tool_calls=[], model="stub",
    ),
    AIResponse(content="Erledigt.", tool_calls=[], model="stub"),
])
```

- Leere Queue → gibt `fallback`-Response zurück (Default: `AIResponse(content="done")`)
- Alle `send_messages()`-Calls werden in `provider.calls` gespeichert
- `supports_tool_calling()` → `False` (Text-Tool-Calls via XML-Parsing)

### Conductor-Test-Pattern

```python
service = ConductorService()
db = _make_conductor_db()  # SimpleNamespace(commit=AsyncMock())

with patch.object(settings, "hivemind_conductor_enabled", True), \
     patch.object(service, "_is_cooldown_active", AsyncMock(return_value=False)), \
     patch.object(service, "_record_dispatch", AsyncMock(return_value=_make_dispatch())), \
     patch.object(service, "_update_dispatch", AsyncMock()), \
     patch.object(service, "_build_prompt", AsyncMock(return_value="prompt")), \
     patch("app.services.agent_threading.AgentThreadService.resolve_context",
           AsyncMock(return_value=_thread_ctx())), \
     patch("app.services.agent_threading.AgentThreadService.record_dispatch_outcome", AsyncMock()), \
     patch("app.services.ai_provider.get_provider", AsyncMock(return_value=ScriptedAIProvider([]))), \
     patch("app.services.agentic_dispatch.agentic_dispatch", AsyncMock(return_value=agentic_result)), \
     patch("app.services.learning_artifacts.capture_dispatch_learning", AsyncMock(return_value=None)):
    result = await service.dispatch(...)
```

**Wichtig:** `AgentThreadService.resolve_context` MUSS immer gepatched werden — die Methode macht echte DB-Queries ohne Error-Handling.

## Debugging-Checkpoints

### Test schlägt mit `TypeError: Can't instantiate abstract class` fehl

Der `AIProvider`-ABC hat 4 abstrakte Methoden: `send_prompt`, `stream_prompt`, `supports_tool_calling`, `default_model`. Alle müssen in Test-Stubs implementiert sein.

### Test schlägt mit `AttributeError: 'SimpleNamespace' has no attribute 'execute'` fehl

`_resolve_dispatch_context` in Conductor macht echte DB-Queries — diese Exception wird aber geloggt und behandelt. Der Fehler ist **zu ignorieren** (im Log erscheint er als `ERROR`, führt aber zu graceful fallback).

Nur wenn **kein** `AgentThreadService.resolve_context`-Patch gesetzt ist, crasht der Test tatsächlich.

### Patch-Pfade

| Was | Patch-Pfad |
|-----|------------|
| Learning aufzeichnen | `app.services.learning_artifacts.capture_dispatch_learning` |
| Provider beschaffen | `app.services.ai_provider.get_provider` |
| Capacity Guard | `app.services.ai_provider.acquire_provider_capacity` |
| Tool-Ausführung | `app.services.agentic_dispatch._execute_tool_call` |
| Agentic Loop (in Conductor) | `app.services.agentic_dispatch.agentic_dispatch` |
| Thread-Kontext | `app.services.agent_threading.AgentThreadService.resolve_context` |
| Thread-Outcome | `app.services.agent_threading.AgentThreadService.record_dispatch_outcome` |
| Settings-Flag | `patch.object(settings, "hivemind_conductor_enabled", True)` |

### Cooldown-Test

`result["status"]` ist `"cooldown_skipped"` (nicht `"skipped"`). `result["skip_reason"]` ist `"cooldown_active"`.

### Fallback-Test

Wenn `agentic_dispatch` eine Exception wirft und `byoai` in der Fallback-Chain steht → `result["status"]` ist `"byoai"`. Falls die Kette keine `byoai`-Option hat → `"failed"` oder `"error"`.

## Vollständige Suite nach Änderungen

Nach Änderungen an `agentic_dispatch.py`, `conductor.py` oder `learning_artifacts.py`:

```bash
podman compose exec backend /app/.venv/bin/pytest tests/ -v --tb=short
```

Erwartete Gesamtzahl: ≥ 76 Tests (47 aus TASK-AGENT-005 + 29 aus TASK-AGENT-007).
