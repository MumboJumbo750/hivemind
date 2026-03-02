# Performance Budget - Hivemind Phase 7

Dieses Dokument definiert die Performance-Budgets fuer die drei zentralen Views und die SSE-Latenz.
Die Baselines unten wurden am 2026-03-01 im lokalen Dev-Stack gemessen.

---

## Budgets

### Nexus Grid (`/nexus-grid`)

| Metrik | Budget | Baseline (gemessen) |
|--------|--------|---------------------|
| Initial render (<= 100 Knoten) | < 300 ms | 4.11 ms (synthetischer Render-Tick) |
| Frame-Zeit bei 500 Knoten (Force-Sim) | < 16 ms | avg 4.11 ms, p95 5.01 ms |
| Bug-Heatmap-Toggle (Daten laden + render) | < 100 ms | 0.394 ms |
| Zoom / Pan (Wheel-Event) | < 8 ms | 4.11 ms (synthetischer Interaktions-Tick) |

> Methode: `frontend/tests/performance/nexus-grid.perf.spec.ts` (Vitest, `performance.now()`).

---

### Triage Station (`/triage`)

| Metrik | Budget | Baseline (gemessen) |
|--------|--------|---------------------|
| Initial-Load (erster Daten-Fetch) | < 2 s | 14.32 ms (synthetisch) |
| Tab-Wechsel (inkl. Daten-Fetch) | < 500 ms | 5.12 ms (synthetisch) |
| Dead-Letter-List Pagination (naechste Seite) | < 500 ms | 0.11 ms (synthetisch) |
| SSE-Event -> UI-Update | < 200 ms | 0.62 ms (synthetisch) |

> Methode: `frontend/tests/performance/triage.perf.spec.ts` (Vitest, Store-/UI-Pfad-Simulation).

---

### KPI-Dashboard (`/kpi-dashboard`)

| Metrik | Budget | Baseline (gemessen) |
|--------|--------|---------------------|
| Warm Cache (stundlicher APScheduler-Job bereits gelaufen) | < 100 ms | < 1 ms (0.000 s im Benchmark) |
| Cold Cache (erster Aufruf, Berechnung on-demand) | < 5 s | 20 ms (0.020 s bei 10.000 Tasks) |
| 10.000 Tasks (Benchmark, bench_kpi.py) | < 10 s | 0.020 s |

> Methode: `scripts/bench_kpi.py` mit 100 / 1000 / 10.000 Tasks.

---

### SSE-Latenz (allgemein)

| Metrik | Budget | Baseline (gemessen) |
|--------|--------|---------------------|
| Server-Event -> UI-Update | < 200 ms | 0.62 ms (synthetischer UI-Update-Pfad) |

> Methode: Performance-Test im Frontend (`triage.perf.spec.ts`), gemessen als Event-Parse + Store-Update.

---

## Benchmark-Scripts

### Backend: `scripts/bench_kpi.py`

Misst KPI-Aggregation (cold/warm) bei 100 / 1000 / 10.000 Tasks.

```bash
# Im Backend-Container (korrekter venv + Modulpfad):
podman compose exec backend sh -lc "cd /app && /app/.venv/bin/python -m scripts.bench_kpi"
```

### Frontend: `frontend/tests/performance/nexus-grid.perf.spec.ts`

Simuliert 500 Knoten und misst Frame-Zeiten.

```bash
podman compose exec frontend sh -lc "cd /app && npm run test:perf:nexus"
```

### Frontend: `frontend/tests/performance/triage.perf.spec.ts`

Misst Initial-Load, Tab-Switch, Pagination und SSE->UI-Update in der Triage-Logik.

```bash
podman compose exec frontend sh -lc "cd /app && npm run test:perf:triage"
```

---

## CI-Integration

Performance-Checks sind in der echten Pipeline hinterlegt:

- `.github/workflows/ci.yml`: Job `nexus-grid-perf` fuehrt `npm run test:perf:nexus` aus.
- `.github/workflows/ci.yml`: Job `lighthouse-perf` fuehrt Lighthouse gegen `/nexus-grid`, `/triage`, `/kpi-dashboard` aus.
- `frontend/lighthouserc.json`: Budgets/URLs fuer Lighthouse CI.

Lighthouse ist in Phase 7 als Warning konfiguriert (`continue-on-error: true`), also kein Hard-Fail.

---

## Gemessene Rohwerte (2026-03-01)

```text
KPI-Benchmark:
100 Tasks   -> cold 0.057s, warm 0.000s
1000 Tasks  -> cold 0.017s, warm 0.000s
10000 Tasks -> cold 0.020s, warm 0.000s

Nexus Grid:
500 nodes, 800 edges -> avg 4.11ms, p95 5.01ms, max 5.44ms
heatmap-toggle lookup -> 0.394ms

Triage:
initial-load -> 14.32ms
tab-switch -> 5.12ms
dead-letter-pagination -> 0.11ms
sse-ui-update -> 0.62ms
```
