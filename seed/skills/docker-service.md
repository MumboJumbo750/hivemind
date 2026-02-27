---
title: "Docker Compose Service konfigurieren"
service_scope: ["devops"]
stack: ["docker", "docker-compose"]
version_range: { "docker-compose": ">=2.0" }
confidence: 0.5
source_epics: ["EPIC-PHASE-1A"]
guards: []
---

## Skill: Docker Compose Service konfigurieren

### Rolle
Du konfigurierst oder erweiterst einen Service im Docker Compose Stack von Hivemind.

### Konventionen
- `docker-compose.yml` im Projektroot
- Services: `postgres`, `backend`, `frontend` (Phase 1), `ollama` (Phase 3+)
- Health-Checks für jeden Service
- Volume-Mounts für Persistenz und Hot-Reload
- Env-Vars via `.env`-Datei (nie in `docker-compose.yml` hardcoden)
- Netzwerk: alle Services im selben Default-Network

### Beispiel

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-hivemind}
      POSTGRES_USER: ${POSTGRES_USER:-hivemind}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-hivemind_dev}
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./backend/app:/app/app
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-hivemind}:${POSTGRES_PASSWORD:-hivemind_dev}@postgres:5432/${POSTGRES_DB:-hivemind}

  frontend:
    build: ./frontend
    command: npm run dev -- --host 0.0.0.0
    volumes:
      - ./frontend/src:/app/src
    ports:
      - "5173:5173"
    depends_on:
      - backend

volumes:
  pgdata:
```

### Wichtig
- `pgvector/pgvector:pg16` statt `postgres:16` (pgvector-Extension vorinstalliert)
- Backend wartet auf `postgres: service_healthy` bevor es startet
- Hot-Reload: nur `app/`-Ordner mounten, nicht den ganzen Container
