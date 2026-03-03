"""Worker Endpoint Pool — Phase 8 (TASK-8-018).

Multi-endpoint load-balancing for self-hosted AI providers (Ollama, custom).
Strategies: round_robin (default), weighted, least_busy.

Health-check: Conductor pings endpoints before dispatch.
Unhealthy endpoints: 60s cooldown before retry.

Only applicable to ollama/custom providers.
Cloud providers (anthropic, openai, github_models) have their own load-balancing.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

UNHEALTHY_COOLDOWN_SECONDS = 60


@dataclass
class PoolEndpoint:
    url: str
    weight: int = 1
    healthy: bool = True
    last_health_check: float = 0.0
    active_dispatches: int = 0
    total_response_time_ms: int = 0
    total_calls: int = 0

    @property
    def avg_response_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_response_time_ms / self.total_calls


class EndpointPool:
    """Load-balancing pool for multiple self-hosted AI endpoints."""

    def __init__(self, endpoints: list[dict], strategy: str = "round_robin"):
        self._endpoints = [
            PoolEndpoint(
                url=e["url"],
                weight=int(e.get("weight", 1)),
            )
            for e in endpoints
        ]
        self._strategy = strategy
        self._rr_index = 0
        self._lock = asyncio.Lock()

    async def get_next_endpoint(self) -> PoolEndpoint | None:
        """Select the next healthy endpoint based on strategy."""
        async with self._lock:
            healthy = [e for e in self._endpoints if e.healthy]
            if not healthy:
                # Check if any unhealthy endpoint has cooled down
                now = time.monotonic()
                for e in self._endpoints:
                    if now - e.last_health_check > UNHEALTHY_COOLDOWN_SECONDS:
                        e.healthy = True  # tentatively mark healthy for retry
                healthy = [e for e in self._endpoints if e.healthy]
            if not healthy:
                return None

            if self._strategy == "weighted":
                return self._weighted_select(healthy)
            elif self._strategy == "least_busy":
                return min(healthy, key=lambda e: e.active_dispatches)
            else:
                # round_robin
                idx = self._rr_index % len(healthy)
                self._rr_index += 1
                return healthy[idx]

    def _weighted_select(self, endpoints: list[PoolEndpoint]) -> PoolEndpoint:
        """Weighted random selection."""
        import random
        total = sum(e.weight for e in endpoints)
        r = random.uniform(0, total)
        cumulative = 0
        for e in endpoints:
            cumulative += e.weight
            if r <= cumulative:
                return e
        return endpoints[-1]

    async def mark_unhealthy(self, url: str) -> None:
        async with self._lock:
            for e in self._endpoints:
                if e.url == url:
                    e.healthy = False
                    e.last_health_check = time.monotonic()
                    logger.warning("Endpoint marked unhealthy: %s", url)
                    break

    async def record_call(self, url: str, response_time_ms: int) -> None:
        async with self._lock:
            for e in self._endpoints:
                if e.url == url:
                    e.total_calls += 1
                    e.total_response_time_ms += response_time_ms
                    break

    def get_status(self) -> list[dict]:
        return [
            {
                "url": e.url,
                "healthy": e.healthy,
                "weight": e.weight,
                "active_dispatches": e.active_dispatches,
                "avg_response_ms": round(e.avg_response_ms, 1),
            }
            for e in self._endpoints
        ]


async def health_check_endpoint(url: str) -> bool:
    """Ping an Ollama/custom endpoint to check availability."""
    import httpx
    try:
        # Try Ollama health check
        async with httpx.AsyncClient() as client:
            # Ollama: GET /api/tags
            resp = await client.get(f"{url.rstrip('/')}/api/tags", timeout=5.0)
            return resp.status_code == 200
    except Exception:
        return False


def build_pool_from_config(config: Any) -> EndpointPool | None:
    """Build an EndpointPool from an AIProviderConfig DB row."""
    if not config.endpoints:
        return None
    endpoints = config.endpoints
    if not isinstance(endpoints, list) or not endpoints:
        return None
    return EndpointPool(
        endpoints=endpoints,
        strategy=config.pool_strategy or "round_robin",
    )
