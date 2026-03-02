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

### Konventionen
- Service in `app/services/conductor.py`
- Model in `app/models/conductor_dispatch.py`
- Conductor wird als Teil des FastAPI-Lifespan gestartet (kein eigener Container)
- Aktivierung via `HIVEMIND_CONDUCTOR_ENABLED=true` (Default: `false`)
- Deaktivierbar pro Projekt (Fallback: manuelle Prompt Station)
- Jeder Dispatch erzeugt einen `conductor_dispatches`-Eintrag (Audit-Trail)
- Idempotenz: `idempotency_key` aus `(event_type, entity_id, timestamp_bucket)` → Doppelte Events = Noop
- Cooldown: `HIVEMIND_CONDUCTOR_COOLDOWN_SECONDS` zwischen Dispatches für denselben Kontext

### Datenmodell

```python
class ConductorDispatch(Base):
    __tablename__ = "conductor_dispatches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    event_type: Mapped[str] = mapped_column(String(100))  # task_state_changed, epic_state_changed, ...
    entity_id: Mapped[str] = mapped_column(String(100))  # TASK-88, EPIC-12, ...
    agent_role: Mapped[str] = mapped_column(String(50))  # worker, gaertner, reviewer, ...
    prompt_type: Mapped[str] = mapped_column(String(50))  # worker, gaertner, review, ...
    provider: Mapped[str | None] = mapped_column(String(50))  # anthropic, ollama, None (BYOAI)
    status: Mapped[str] = mapped_column(String(20), default="dispatched")  # dispatched, completed, failed, byoai
    tokens_used: Mapped[int | None] = mapped_column()
    error_message: Mapped[str | None] = mapped_column(Text)
    dispatched_at: Mapped[datetime] = mapped_column(default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column()
```

### Die 12 Dispatch-Regeln (kanonisch)

| # | Trigger-Event | Bedingung | Agent | Prompt-Typ |
|---|---------------|-----------|-------|------------|
| 1 | Epic `incoming → scoped` | `governance.epic_scoping = 'auto'` | Architekt | `architekt` |
| 2 | Epic `incoming` (neu) | `governance.epic_scoping = 'auto'` | Auto-Scope (intern) | — |
| 3 | Task `scoped → ready` | — | Worker (nach Bibliothekar) | `worker` |
| 4 | Task `in_review` | `governance.review ≠ 'manual'` | Reviewer | `review` |
| 5 | Task `done` | — | Gaertner | `gaertner` |
| 6 | `[UNROUTED]` Event | — | Triage | `triage` |
| 7 | `[EPIC PROPOSAL]` eingereicht | `governance.epic_proposals = 'auto'` | Triage (auto-accept) | `triage` |
| 8 | `[SKILL PROPOSAL]` eingereicht | `governance.skill_merge = 'auto'` | Auto-Merge-Check | — |
| 9 | Projekt erstellt + Repo | — | Kartograph | `kartograph` |
| 10 | Kartograph-Session beendet | Plan vorhanden | Stratege | `stratege` |
| 11 | GitLab `push`-Event | Follow-up nötig | Kartograph | `kartograph` |
| 12 | `decision_request` erstellt | `governance.decisions ≠ 'manual'` | Decision-Resolver | — |

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
            case "ready":
                await self._dispatch("worker", "worker", task_key=event.task_key)
            case "in_review":
                await self._dispatch_review(event.task_key)
            case "done":
                await self._dispatch("gaertner", "gaertner", task_key=event.task_key)

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

### Konfiguration

| Env-Variable | Default | Beschreibung |
| --- | --- | --- |
| `HIVEMIND_CONDUCTOR_ENABLED` | `false` | Conductor aktivieren |
| `HIVEMIND_CONDUCTOR_PARALLEL` | `3` | Max. gleichzeitige Agent-Dispatches |
| `HIVEMIND_CONDUCTOR_COOLDOWN_SECONDS` | `10` | Mindestzeit zwischen Dispatches für denselben Kontext |

### Wichtige Regeln
- Conductor reagiert **nur** auf Events — er initiiert nie selbst eine Aktion ohne Auslöser
- Conductor hat **keine AI-Intelligenz** — er ist ein deterministischer Dispatcher
- Jeder Dispatch **muss** einen `conductor_dispatches`-Eintrag schreiben (Audit-Trail)
- BYOAI-Fallback ist **immer** möglich — nicht-konfigurierte Rollen bleiben manuell
- Conductor ist per `HIVEMIND_CONDUCTOR_ENABLED` deaktivierbar (Default: aus)
- APScheduler-Job Registrierung: in `app/services/scheduler.py` → `start_scheduler()` — **nie** in `main.py`
