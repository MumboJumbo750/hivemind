.PHONY: help \
        up up-ai down ps \
        logs logs-be logs-fe \
        restart-be restart-fe \
        rebuild rebuild-be rebuild-fe \
        test test-be test-integration test-install \
        migrate shell-be db \
        check lint typecheck arch fix check-docker \
        health health-json health-md health-test health-scan

VENV := /app/.venv/bin

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Hivemind — Dev Commands"
	@echo ""
	@echo "  Stack:"
	@echo "    make up              Start stack (ohne Ollama)"
	@echo "    make up-ai           Start stack + Ollama (Phase 3+)"
	@echo "    make down            Stack stoppen"
	@echo "    make ps              Service-Status"
	@echo ""
	@echo "  Logs & Neustart:"
	@echo "    make logs            Backend-Logs (live)"
	@echo "    make logs-fe         Frontend-Logs (live)"
	@echo "    make restart-be      Backend neustarten (dep-check re-installiert Deps)"
	@echo "    make restart-fe      Frontend neustarten"
	@echo ""
	@echo "  Rebuild (nur bei Dockerfile/System-Dep Änderungen):"
	@echo "    make rebuild-be      Backend-Image neu bauen + starten"
	@echo "    make rebuild-fe      Frontend-Image neu bauen + starten"
	@echo "    make rebuild         Alles neu bauen + starten"
	@echo ""
	@echo "  Tests:"
	@echo "    make test-install    Test-Deps im Container installieren (einmalig)"
	@echo "    make test            Alle Backend-Tests"
	@echo "    make test-be         Alle Backend-Tests (explizit)"
	@echo "    make test-integration Nur Integration-Tests"
	@echo ""
	@echo "  Datenbank:"
	@echo "    make migrate         alembic upgrade head"
	@echo "    make shell-be        bash im Backend-Container"
	@echo "    make db              psql im Postgres-Container"
	@echo ""
	@echo "  Code-Qualität (lokal):"
	@echo "    make check           Alle Checks (arch + lint + typecheck)"
	@echo "    make fix             Auto-Fix (ruff + eslint)"
	@echo "    make check-docker    Alle Checks via Container (ohne lokale Tools)"
	@echo ""
	@echo "  Health & Analyzer:"
	@echo "    make health          Repo Health Scan (text output)"
	@echo "    make health-json     Repo Health Scan → health_report.json"
	@echo "    make health-md       Repo Health Scan → health_report.md"
	@echo "    make health-scan     Alias fuer make health"
	@echo "    make health-test     Analyzer-Unit-Tests im Container"
	@echo ""

up:
	podman compose up -d

up-ai:
	podman compose --profile ai up -d

down:
	podman compose down

ps:
	podman compose ps

# ── Logs & Status ─────────────────────────────────────────────────────────────
logs:
	podman compose logs -f backend

logs-be:
	podman compose logs -f backend

logs-fe:
	podman compose logs -f frontend

# ── Neustart (dep-check.sh re-installiert Deps automatisch) ───────────────────
#
#   Wann reicht restart (KEIN rebuild nötig)?
#     - requirements.txt geändert → dep-check.sh re-installiert beim Neustart
#     - Konfiguration (.env) geändert
#     - Code-Änderungen brauchen NICHTS (Hot-Reload via Volume-Mount)
#
restart-be:
	podman compose restart backend

restart-fe:
	podman compose restart frontend

# ── Rebuild (nur bei Dockerfile oder System-Dep Änderungen) ──────────────────
#
#   Wann ist rebuild nötig?
#     - backend/Dockerfile geändert
#     - Neue System-Abhängigkeiten (apt-get install)
#     - Größere Image-Änderungen
#   Wann NICHT?
#     - requirements.txt geändert → make restart-be reicht
#     - Code geändert           → Hot-Reload, nichts nötig
#
rebuild-be:
	podman compose build backend
	podman compose up -d backend

rebuild-fe:
	podman compose build frontend
	podman compose up -d frontend

rebuild:
	podman compose build
	podman compose up -d

# ── Tests ─────────────────────────────────────────────────────────────────────
#
#   Test-Deps (pytest, testcontainers, respx, etc.) sind in requirements-dev.txt,
#   aber NICHT im Production-Image. test-install installiert sie im laufenden
#   Container. Dieser Schritt ist idempotent (pip install ist safe to repeat).
#
#   Wichtig: Backend muss laufen → `make up` zuerst.
#
test-install:
	podman compose exec backend $(VENV)/pip install -q -r /app/requirements-dev.txt

test-be: test-install
	podman compose exec backend $(VENV)/pytest tests/ -v

test-integration: test-install
	podman compose exec backend $(VENV)/pytest tests/integration/ -v --tb=short

test: test-be

# ── Datenbank ─────────────────────────────────────────────────────────────────
migrate:
	podman compose exec backend $(VENV)/alembic upgrade head

shell-be:
	podman compose exec backend bash

db:
	podman compose exec postgres psql -U hivemind hivemind

# ── Alle Checks in einem Befehl ────────────────────────────────────────────────
check: arch lint typecheck
	@echo "\n✓  Alle Checks bestanden."

# ── Architektur + Dateigrößen ─────────────────────────────────────────────────
arch:
	@echo "→ arch-check..."
	python scripts/arch-check.py

# ── Linting ───────────────────────────────────────────────────────────────────
lint: lint-fe lint-be

lint-fe:
	@echo "→ eslint (frontend)..."
	cd frontend && npm run lint

lint-be:
	@echo "→ ruff (backend)..."
	cd backend && ruff check .

# ── Type-Checking ─────────────────────────────────────────────────────────────
typecheck: typecheck-fe typecheck-be

typecheck-fe:
	@echo "→ vue-tsc (frontend)..."
	cd frontend && npm run typecheck

typecheck-be:
	@echo "→ mypy (backend)..."
	cd backend && mypy app/

# ── Auto-Fix ──────────────────────────────────────────────────────────────────
fix: fix-fe fix-be

fix-fe:
	@echo "→ eslint --fix (frontend)..."
	cd frontend && npm run lint:fix

fix-be:
	@echo "→ ruff format + fix (backend)..."
	cd backend && ruff format . && ruff check --fix .

# ── Repo Health Scanner ──────────────────────────────────────────────────────
health: ## Repo Health Scan (text output)
	@echo "→ Repo Health Scanner..."
	podman compose run --rm --no-deps --entrypoint="" \
		-v "$(CURDIR):/workspace:ro" -w /workspace backend \
		/app/.venv/bin/python scripts/health_check.py --root .

health-json: ## Repo Health Scan → health_report.json
	@echo "→ Repo Health Scanner (JSON)..."
	podman compose run --rm --no-deps --entrypoint="" \
		-v "$(CURDIR):/workspace" -w /workspace backend \
		/app/.venv/bin/python scripts/health_check.py --root . --format json --output health_report.json

health-md: ## Repo Health Scan → health_report.md
	@echo "→ Repo Health Scanner (Markdown)..."
	podman compose run --rm --no-deps --entrypoint="" \
		-v "$(CURDIR):/workspace" -w /workspace backend \
		/app/.venv/bin/python scripts/health_check.py --root . --format markdown --output health_report.md

# ── Analyzer Tests im Container ─────────────────────────────────────────────
health-scan: health ## Alias: Repo Health Scan (text output)

health-test: ## Analyzer-Unit-Tests im Container ausfuehren
	@echo "→ Analyzer-Tests im Container..."
	podman compose exec -w /workspace -e PYTHONPATH=/workspace:/app backend \
		$(VENV)/pytest scripts/analyzers/tests/ -v

# ── VS Code Extension ────────────────────────────────────────────────────────
ext-build: ## Extension kompilieren + in VS Code installieren (dann Reload Window)
	@echo "→ Extension bauen & deployen..."
	cd vscode-extension && npm run compile
	@echo "✓ Fertig — VS Code neu laden: Ctrl+Shift+P → Developer: Reload Window"

ext-watch: ## Extension im Watch-Modus bauen (kein Auto-Deploy)
	@echo "→ Extension watch..."
	cd vscode-extension && npm run watch

# ── Container-Varianten (wenn Tools nicht lokal installiert sind) ─────────────
check-docker:
	podman compose run --rm frontend npm run lint
	podman compose run --rm frontend npm run typecheck
	podman compose run --rm backend $(VENV)/ruff check .
	podman compose run --rm backend $(VENV)/mypy app/
	python scripts/arch-check.py
