#!/bin/bash
set -e

echo "[backend] Running Alembic migrations..."
/app/.venv/bin/alembic upgrade head
echo "[backend] Migrations complete."

echo "[backend] Starting Uvicorn..."
exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 3
