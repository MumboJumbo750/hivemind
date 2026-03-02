---
title: "Worker-Endpoint-Pool: Multi-Endpoint Load-Balancing"
service_scope: ["backend"]
stack: ["python", "fastapi", "httpx", "asyncio"]
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

## Skill: Worker-Endpoint-Pool

### Rolle
Du implementierst Multi-Endpoint-Support für Self-Hosted AI-Provider. Statt einem einzelnen Endpoint pro Agent-Rolle können mehrere Endpoints als Pool konfiguriert werden — z.B. mehrere Ollama-Instanzen auf verschiedenen GPUs. Der Conductor dispatcht parallele Tasks an verschiedene Endpoints.

### Kontext
Dieses Feature ist **optional** und funktioniert nur mit `ollama`/`custom`-Providern (Self-Hosted). Cloud-Provider (Anthropic, OpenAI, Google) haben eigenes Load-Balancing. Das Feature erweitert `ai_provider_configs` um ein `endpoints` JSONB-Array.

### Konventionen
- Erweiterung in `app/services/ai_provider_service.py` (bestehender Service)
- Pool-Konfiguration in `ai_provider_configs.endpoints` (JSONB)
- Pool-Strategien: `round_robin` (Default), `weighted`, `least_busy`
- Health-Check per Ping vor Dispatch; unhealthy Endpoints → 60s Cooldown
- RPM-Limit gilt **pro Endpoint** (nicht aggregiert)
- Kein Pflicht-Feature — Single-Endpoint funktioniert weiterhin

### Datenstruktur

```python
# In ai_provider_configs.endpoints (JSONB):
# Wenn endpoints gesetzt → Pool-Modus; wenn null → Single-Endpoint-Modus (endpoint-Feld)
[
    {"url": "http://gpu1:11434", "weight": 2, "name": "RTX 4090"},
    {"url": "http://gpu2:11434", "weight": 1, "name": "RTX 3080"},
    {"url": "http://gpu3:11434", "weight": 1, "name": "RTX 3070"},
]

# Pool-Strategie in ai_provider_configs (neues Feld):
# pool_strategy: "round_robin" | "weighted" | "least_busy"
```

### Pool-Service

```python
import asyncio
import time
from dataclasses import dataclass, field

@dataclass
class EndpointState:
    url: str
    weight: int = 1
    name: str = ""
    healthy: bool = True
    last_health_check: float = 0.0
    active_dispatches: int = 0
    unhealthy_until: float = 0.0  # Cooldown timestamp
    avg_response_ms: float = 0.0
    _response_times: list[float] = field(default_factory=list)

class EndpointPool:
    def __init__(self, endpoints: list[dict], strategy: str = "round_robin"):
        self.endpoints = [EndpointState(**ep) for ep in endpoints]
        self.strategy = strategy
        self._rr_index = 0
        self._lock = asyncio.Lock()

    async def acquire(self) -> EndpointState | None:
        """Wählt nächsten gesunden Endpoint nach Strategie."""
        async with self._lock:
            healthy = [ep for ep in self.endpoints if self._is_healthy(ep)]
            if not healthy:
                return None

            match self.strategy:
                case "round_robin":
                    ep = healthy[self._rr_index % len(healthy)]
                    self._rr_index += 1
                case "weighted":
                    ep = self._weighted_select(healthy)
                case "least_busy":
                    ep = min(healthy, key=lambda e: e.active_dispatches)
                case _:
                    ep = healthy[0]

            ep.active_dispatches += 1
            return ep

    def release(self, endpoint: EndpointState, response_ms: float):
        """Gibt Endpoint nach Dispatch frei."""
        endpoint.active_dispatches -= 1
        endpoint._response_times.append(response_ms)
        if len(endpoint._response_times) > 20:
            endpoint._response_times = endpoint._response_times[-20:]
        endpoint.avg_response_ms = sum(endpoint._response_times) / len(endpoint._response_times)

    def mark_unhealthy(self, endpoint: EndpointState):
        """Markiert Endpoint als unhealthy mit 60s Cooldown."""
        endpoint.healthy = False
        endpoint.unhealthy_until = time.monotonic() + 60.0

    def _is_healthy(self, ep: EndpointState) -> bool:
        if not ep.healthy and time.monotonic() >= ep.unhealthy_until:
            ep.healthy = True  # Cooldown abgelaufen → wieder versuchen
        return ep.healthy

    def _weighted_select(self, healthy: list[EndpointState]) -> EndpointState:
        import random
        total = sum(ep.weight for ep in healthy)
        r = random.uniform(0, total)
        for ep in healthy:
            r -= ep.weight
            if r <= 0:
                return ep
        return healthy[-1]

    async def health_check_all(self, client: httpx.AsyncClient):
        """Prüft alle Endpoints via Ping (Ollama: GET /api/tags)."""
        for ep in self.endpoints:
            try:
                resp = await client.get(f"{ep.url}/api/tags", timeout=5.0)
                ep.healthy = resp.status_code == 200
                ep.last_health_check = time.monotonic()
            except Exception:
                self.mark_unhealthy(ep)
```

### Integration in AI-Provider-Service

```python
class AIProviderService:
    async def send(self, agent_role: str, prompt: str, tools: list[dict]) -> AIResponse | None:
        config = await self._get_config(agent_role)
        if not config:
            return None

        # Pool-Modus oder Single-Endpoint?
        if config.endpoints:
            pool = self._get_or_create_pool(agent_role, config.endpoints, config.pool_strategy)
            endpoint = await pool.acquire()
            if not endpoint:
                raise AIProviderError("All endpoints unhealthy")
            try:
                start = time.monotonic()
                provider = self._create_provider(config, endpoint_url=endpoint.url)
                await self.rate_limiter.acquire(f"{agent_role}:{endpoint.url}", config.rpm_limit)
                result = await send_with_retry(provider, prompt, tools)
                pool.release(endpoint, (time.monotonic() - start) * 1000)
                return result
            except Exception as e:
                pool.mark_unhealthy(endpoint)
                raise
        else:
            # Standard Single-Endpoint
            provider = self._create_provider(config)
            await self.rate_limiter.acquire(agent_role, config.rpm_limit)
            return await send_with_retry(provider, prompt, tools)
```

### Subtask-Aggregation

Wenn alle Subtasks eines Parent-Tasks `done` sind, erzeugt der Conductor einen Merge-Prompt:

```python
# In conductor.py:
async def on_task_done(self, task_key: str):
    async with self.db_factory() as db:
        task = await TaskService(db).get_by_key(task_key)
        parent = await TaskService(db).get_parent(task)

        if parent:
            siblings = await TaskService(db).get_subtasks(parent.key)
            if all(s.state == "done" for s in siblings):
                # Alle Subtasks fertig → Merge-Prompt für Parent
                await self._dispatch("architekt", "merge_subtasks", task_key=parent.key)
```

### Monitoring-Daten (für Frontend)

```python
@router.get("/api/settings/ai-providers/{role}/pool-status")
async def get_pool_status(role: str):
    """Gibt Pool-Status pro Endpoint zurück (für Prompt Station Monitoring)."""
    pool = ai_provider_service.get_pool(role)
    if not pool:
        return {"pool": None}
    return {"pool": [
        {
            "url": ep.url,
            "name": ep.name,
            "healthy": ep.healthy,
            "active_dispatches": ep.active_dispatches,
            "avg_response_ms": round(ep.avg_response_ms, 1),
        }
        for ep in pool.endpoints
    ]}
```

### Wichtige Regeln
- Pool ist **optional** — Single-Endpoint bleibt Standard
- Nur für `ollama`/`custom`-Provider sinnvoll (Cloud-Provider haben eigenes LB)
- RPM-Limit pro Endpoint (ermöglicht höheren Gesamt-Throughput)
- Health-Check vor jedem Dispatch; unhealthy → 60s Cooldown
- Kein Thread-Blocking — alles über asyncio
