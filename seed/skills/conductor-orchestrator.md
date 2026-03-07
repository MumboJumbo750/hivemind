---
title: "Conductor-Orchestrator: Event-driven Agent-Dispatcher"
service_scope: ["backend"]
stack: ["python", "fastapi", "sqlalchemy", "asyncio"]
version_range: { "python": ">=3.11", "fastapi": ">=0.100" }
confidence: 0.5
source_epics: ["EPIC-PHASE-8"]
guards:
  - title: "Python Linting"
    command: "ruff check ."
  - title: "Type Check"
    command: "mypy app/"
  - title: "Tests"
    command: "pytest tests/ -v"
---

## Skill: Conductor-Orchestrator

### Rolle
Du implementierst den Conductor — einen event-getriebenen Backend-Service der auf State-Transitions reagiert und den nächsten AI-Agenten dispatcht. Der Conductor ist das serverseitige Äquivalent der Prompt Station und der Motor des Autonomy Loops in Phase 8.

### Kontext
Der Conductor ist **kein Agent** (keine AI-Intelligenz), sondern ein deterministischer Dispatcher. Er reagiert auf Events (SSE, State-Transitions), schaut in den `ai_provider_configs` nach dem konfigurierten Provider für die jeweilige Agent-Rolle und dispatcht den Prompt. Nicht-konfigurierte Rollen → BYOAI-Fallback (Prompt Station zeigt Prompt).
Manuelle Dispatches aus der Prompt Station laufen ueber `/api/admin/conductor/dispatch`: der Request enthaelt `agent_role` plus Entity-Kontext (`task_key`, `epic_id`, `project_id`) und der Backend-Endpoint generiert daraus zuerst den passenden Prompt.

### Konventionen
- Service in `app/services/conductor.py`
- Model in `app/models/conductor.py`
- Conductor wird als Teil des FastAPI-Lifespan gestartet (kein eigener Container)
- Aktivierung via `HIVEMIND_CONDUCTOR_ENABLED=true`
- Deaktivierbar pro Projekt (Fallback: manuelle Prompt Station)
- Jeder Dispatch erzeugt einen `conductor_dispatches`-Eintrag (Audit-Trail)
- Dedup/Cooldown via `cooldown_key = "{agent_role}:{trigger_id}:{bucket}"`
- Execution Modes: `local`, `ide`, `github_actions`, `byoai`
- Fallback-Chain ist pro Regel konfigurierbar; z.B. `ide -> local -> byoai`
- Lokale Tool-Ausfuehrung fuer `/admin/conductor/dispatch` nutzt `agentic_dispatch()` mit rollenabhaengiger MCP-Tool-Allowlist
- `execution_mode='local'` soll auch im automatischen Workflow ueber `agentic_dispatch()` laufen, damit MCP-Tools wirklich ausgefuehrt werden
- Die Trigger fuer Governance-relevante Flows muessen sowohl in REST-Services als auch in MCP-Write-Tools verdrahtet sein

### Datenmodell

```python
class ConductorDispatch(Base):
    __tablename__ = "conductor_dispatches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    trigger_type: Mapped[str] = mapped_column(String(50))      # task_state, event, epic_state, ...
    trigger_id: Mapped[str] = mapped_column(String(200))       # TASK-88, EPIC-12, decision-id, ...
    trigger_detail: Mapped[str | None] = mapped_column(String(500))
    agent_role: Mapped[str] = mapped_column(String(50))        # worker, gaertner, reviewer, ...
    prompt_type: Mapped[str | None] = mapped_column(String(100))
    execution_mode: Mapped[str] = mapped_column(String(20))    # local, ide, github_actions, byoai
    status: Mapped[str] = mapped_column(String(20), default="dispatched")
    cooldown_key: Mapped[str | None] = mapped_column(String(300))
    result: Mapped[dict | None] = mapped_column(JSONB)         # prompt, tokens, tool_calls, error, progress, ...
    dispatched_at: Mapped[datetime] = mapped_column(default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column()
```

### Die Dispatch-Regeln (kanonisch)

| # | Trigger-Event | Bedingung | Agent | Prompt-Typ |
|---|---------------|-----------|-------|------------|
| 1 | Task `scoped -> in_progress` | Regel `task_scoped_to_in_progress` | Worker | `worker_implement` |
| 2 | Task `in_progress -> in_review` | Governance `review != manual` | Reviewer | `reviewer_check` |
| 3 | Task `done` | Regel `task_done` | Gaertner | `gaertner_harvest` |
| 4 | Task `qa_failed` | Regel `task_qa_failed` | Gaertner | `gaertner_review_feedback` |
| 5 | Task `incoming -> scoped` | Governance `epic_scoping != manual` | Architekt | `architekt_decompose` |
| 6 | `[UNROUTED]` Inbound-Event | Regel `event_unrouted_inbound` | Triage | `triage_classify` |
| 7 | Epic erstellt | Governance `epic_scoping != manual` | Stratege | `stratege_plan` |
| 8 | Epic `incoming -> scoped` | Regel `epic_scoped` | Architekt | `architekt_decompose` |
| 9 | Epic-Proposal eingereicht | Governance `epic_proposal != manual` | Triage | `triage_epic_proposal` |
| 10 | Skill-Proposal eingereicht | Governance `skill_merge != manual` | Triage | `triage_skill_proposal` |
| 11 | Guard-Proposal eingereicht | Governance `guard_merge != manual` | Triage | `triage_guard_proposal` |
| 12 | Epic-Restructure vorgeschlagen | Regel `epic_restructure_proposed` | Triage | `triage_epic_restructure` |
| 13 | Projekt erstellt | Regel `project_created` | Kartograph | `kartograph_explore` |
| 14 | Push-Event | Regel `push_event` | Kartograph | `kartograph_follow_up` |
| 15 | Decision Request offen | Governance `decision_request != manual` | Triage | `triage_decision_request` |

Wichtig zum Ist-Stand:
- `manual` blockiert den automatischen Dispatch.
- `assisted` und `auto` loesen fuer die meisten Governance-Typen heute denselben Dispatch aus.
- Der explizite Unterschied zwischen `assisted` und `auto` ist aktuell nur fuer `review` mit Grace-Period/Auto-Approve voll implementiert.
- Skill-, Guard- und Epic-Restructure-Proposals gehen im Auto-/Assisted-Modus ueber Triage-Review statt ueber den Gaertner selbst.
- `guard_merge` startet keinen separaten Folge-Agenten; der operative Effekt eines gemergten Guards ist die sofortige Materialisierung auf passende Tasks.

### Implementierung

```python
import asyncio
from datetime import datetime, timedelta

class Conductor:
    """Event-getriebener Orchestrator für Phase 8 Auto-Modus."""

    def __init__(self, db_factory, ai_provider_service, prompt_generator):
        self.db_factory = db_factory
        self.ai_service = ai_provider_service
        self.prompt_gen = prompt_generator
        self._semaphore = asyncio.Semaphore(settings.conductor_parallel)
        self._cooldowns: dict[str, datetime] = {}

    async def on_task_state_changed(self, event: TaskStateChanged):
        match event.new_state:
            case "in_progress" if event.old_state == "scoped":
                await self._dispatch("worker", "worker", task_key=event.task_key)
            case "in_review":
                await self._dispatch_review(event.task_key)
            case "done":
                await self._dispatch("gaertner", "gaertner", task_key=event.task_key)
            case "qa_failed":
                await self._dispatch("gaertner", "gaertner_review_feedback", task_key=event.task_key)

    async def on_epic_state_changed(self, event: EpicStateChanged):
        match event.new_state:
            case "scoped":
                await self._dispatch("architekt", "architekt", epic_key=event.epic_key)

    async def on_unrouted_event(self, event: UnroutedEvent):
        await self._dispatch("triage", "triage")

    async def _dispatch(self, agent_role: str, prompt_type: str, **kwargs):
        """Generiert Prompt, prüft Idempotenz/Cooldown, sendet an AI-Provider."""
        entity_id = kwargs.get("task_key") or kwargs.get("epic_key") or "global"
        idempotency_key = f"{agent_role}:{entity_id}:{self._time_bucket()}"

        # Idempotenz-Check
        async with self.db_factory() as db:
            existing = await db.scalar(
                select(ConductorDispatch).where(
                    ConductorDispatch.idempotency_key == idempotency_key
                )
            )
            if existing:
                return  # Doppeltes Event → Noop

            # Cooldown-Check
            cooldown_key = f"{agent_role}:{entity_id}"
            if cooldown_key in self._cooldowns:
                if datetime.utcnow() - self._cooldowns[cooldown_key] < timedelta(
                    seconds=settings.conductor_cooldown_seconds
                ):
                    return  # Cooldown aktiv

            # Dispatch-Eintrag erstellen
            dispatch = ConductorDispatch(
                idempotency_key=idempotency_key,
                event_type=f"{agent_role}_dispatch",
                entity_id=entity_id,
                agent_role=agent_role,
                prompt_type=prompt_type,
                status="dispatched",
            )
            db.add(dispatch)
            await db.commit()

        # Prompt generieren + an Provider senden (mit Semaphore)
        async with self._semaphore:
            try:
                prompt = await self.prompt_gen.generate(prompt_type, **kwargs)
                tools = await self._get_tools_for_role(agent_role)
                response = await self.ai_service.send(agent_role, prompt, tools)

                if response is None:
                    # BYOAI-Fallback — kein Provider konfiguriert
                    await self._update_dispatch(dispatch.id, "byoai")
                else:
                    # MCP-Tool-Calls aus AI-Response ausführen
                    await self._execute_tool_calls(response.tool_calls)
                    await self._update_dispatch(
                        dispatch.id, "completed", tokens_used=response.tokens_used
                    )
            except Exception as e:
                await self._update_dispatch(dispatch.id, "failed", error=str(e))

        self._cooldowns[cooldown_key] = datetime.utcnow()

    async def _dispatch_review(self, task_key: str):
        """Review-Dispatch mit Governance-Level."""
        governance = await self._get_governance()
        match governance.get("review", "manual"):
            case "manual":
                pass  # Prompt Station zeigt Review-Prompt
            case "assisted" | "auto":
                await self._dispatch("reviewer", "review", task_key=task_key)

    def _time_bucket(self) -> str:
        """10-Sekunden-Bucket für Idempotenz."""
        now = int(datetime.utcnow().timestamp())
        return str(now - (now % 10))
```

### Parallelität & Backpressure

- `asyncio.Semaphore(HIVEMIND_CONDUCTOR_PARALLEL)` begrenzt gleichzeitige Dispatches (Default: 3)
- Unabhängige Dispatches (z.B. mehrere Tasks `ready`) → `asyncio.gather()` parallel
- Abhängige Dispatches (Bibliothekar → Worker) → sequenziell
- RPM-Limit als primäre Backpressure (→ `ai-provider-service` Skill)
- Keine externe Message Queue nötig für Single-Node-Betrieb

### Prompt-Aufloesung & manueller Run

- `conductor.dispatch()` baut Prompts serverseitig ueber `PromptGenerator.generate(...)`
- `agent_role` bestimmt `prompt_type` und die Tool-Allowlist
- Der manuelle Endpoint `/api/admin/conductor/dispatch` loest bei vorhandenem Kontext den Prompt immer neu auf
- Die Prompt Station darf beim Klick auf `Ausfuehren` keinen Rohtext wie `task.description` senden, sondern muss den ausgewaehlten Agenten-Prompt verwenden
- Proposal-/Decision-Dispatches muessen den passenden Prompt-Kontext aufloesen:
  - `skill:proposal` → `skill_id`
  - `guard:proposal` → `guard_id`
  - `epic_proposal:submitted` → `proposal_id`
  - `decision_request:open` / `epic_restructure:proposed` → `decision_id`

### Self-Improvement-Regeln

- Auto-Review darf nie am Review-Workflow vorbei direkt `done` setzen.
- `task_done` und `task_qa_failed` sind beide Lerntrigger fuer den Gaertner.
- Reicht der Gaertner einen Skill-Entwurf ein (`submit_skill_proposal`), uebernimmt anschliessend Triage die Review-/Merge-Entscheidung.
- Reicht der Kartograph einen Guard oder ein Epic-Restructure ein, uebernimmt ebenfalls Triage die Entscheidung.

### Konfiguration

| Env-Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_CONDUCTOR_ENABLED` | `true` im Compose-Default | Conductor aktivieren |
| `HIVEMIND_CONDUCTOR_PARALLEL` | `3` | Max. gleichzeitige Agent-Dispatches |
| `HIVEMIND_CONDUCTOR_COOLDOWN_SECONDS` | `10` | Mindestzeit zwischen Dispatches für denselben Kontext |

### Wichtige Regeln
- Conductor reagiert **nur** auf Events — er initiiert nie selbst eine Aktion ohne Auslöser
- Conductor hat **keine AI-Intelligenz** — er ist ein deterministischer Dispatcher
- Jeder Dispatch **muss** einen `conductor_dispatches`-Eintrag schreiben (Audit-Trail)
- BYOAI-Fallback ist **immer** möglich — nicht-konfigurierte Rollen bleiben manuell
- Conductor ist per `HIVEMIND_CONDUCTOR_ENABLED` deaktivierbar (Default: aus)
- APScheduler-Job Registrierung: in `app/services/scheduler.py` → `start_scheduler()` — **nie** in `main.py`
