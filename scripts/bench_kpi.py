#!/usr/bin/env python3
"""KPI benchmark for TASK-7-018.

Measures get_or_compute_kpis() runtime for different task volumes.
Run inside backend container:

    podman compose exec backend sh -lc "cd /app && /app/.venv/bin/python -m scripts.bench_kpi"

Prerequisite: database connection available via DATABASE_URL.
"""
from __future__ import annotations

import asyncio
import time
import uuid

from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.services.kpi_service import get_or_compute_kpis

BENCH_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def _seed_tasks(db, count: int) -> tuple[list[uuid.UUID], uuid.UUID, uuid.UUID]:
    """Insert synthetic tasks and return (task_ids, epic_id, project_id)."""
    # Ensure a project + epic + actor exist.
    proj_id = uuid.uuid4()
    epic_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]

    await db.execute(
        text(
            "INSERT INTO users (id, username, role, created_at) "
            "VALUES (:id, :username, 'admin', now()) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": str(BENCH_ACTOR_ID), "username": "solo"},
    )

    await db.execute(
        text(
            "INSERT INTO projects (id, name, slug, created_by, created_at) "
            "VALUES (:id, :name, :slug, :created_by, now())"
        ),
        {
            "id": str(proj_id),
            "name": f"bench-project-{suffix}",
            "slug": f"bench-{suffix}",
            "created_by": str(BENCH_ACTOR_ID),
        },
    )
    await db.execute(
        text(
            "INSERT INTO epics (id, epic_key, project_id, title, owner_id, state, version, created_at) "
            "VALUES (:id, :key, :proj, :title, :owner_id, 'in_progress', 1, now())"
        ),
        {
            "id": str(epic_id),
            "key": f"BENCH-{suffix}",
            "proj": str(proj_id),
            "title": f"Bench Epic {suffix}",
            "owner_id": str(BENCH_ACTOR_ID),
        },
    )

    ids: list[uuid.UUID] = []
    for i in range(count):
        task_id = uuid.uuid4()
        state = "done" if i % 3 != 0 else "qa_failed"
        await db.execute(
            text(
                "INSERT INTO tasks (id, task_key, epic_id, title, state, version, created_at, updated_at) "
                "VALUES (:id, :key, :epic, :title, :state, 1, now(), now())"
            ),
            {
                "id": str(task_id),
                "key": f"BENCH-TASK-{i}",
                "epic": str(epic_id),
                "title": f"Bench Task {i}",
                "state": state,
            },
        )
        ids.append(task_id)

    await db.commit()
    return ids, epic_id, proj_id


async def _cleanup_tasks(
    db,
    task_ids: list[uuid.UUID],
    epic_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    if not task_ids:
        return
    id_strs = [str(t) for t in task_ids]
    await db.execute(
        text(f"DELETE FROM tasks WHERE id = ANY(ARRAY[{','.join(repr(s) for s in id_strs)}]::uuid[])")
    )
    await db.execute(text("DELETE FROM epics WHERE id = :id"), {"id": str(epic_id)})
    await db.execute(text("DELETE FROM projects WHERE id = :id"), {"id": str(project_id)})
    await db.commit()


async def run_benchmark(task_count: int) -> tuple[float, float]:
    """Return (cold_seconds, warm_seconds)."""
    from app.services import kpi_service as _ks

    # Invalidate in-process KPI cache before each run.
    _ks._kpi_cache.clear()
    _ks._computed_at = None

    async with AsyncSessionLocal() as db:
        task_ids, epic_id, project_id = await _seed_tasks(db, task_count)

    t0_cold = time.perf_counter()
    await get_or_compute_kpis()  # cold
    cold_elapsed = time.perf_counter() - t0_cold

    t0_warm = time.perf_counter()
    await get_or_compute_kpis()  # warm (cached)
    warm_elapsed = time.perf_counter() - t0_warm

    # Cleanup synthetic entities.
    async with AsyncSessionLocal() as db:
        await _cleanup_tasks(db, task_ids, epic_id, project_id)

    return cold_elapsed, warm_elapsed


async def main() -> None:
    print("KPI benchmark (TASK-7-018)")
    print("=" * 40)

    for count in (100, 1000, 10_000):
        print(f"\nRun with {count:>6} tasks ...", end=" ", flush=True)
        try:
            cold_elapsed, warm_elapsed = await run_benchmark(count)
            status = "OK" if cold_elapsed < 10 else "SLOW"
            print(
                f"cold: {cold_elapsed:.3f}s, warm: {warm_elapsed:.3f}s  [{status}]"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: {exc}")

    print("\nBudget: <= 10s for 10,000 tasks (warm cache <= 0.1s)")


if __name__ == "__main__":
    asyncio.run(main())
