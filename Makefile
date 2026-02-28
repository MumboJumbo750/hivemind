.PHONY: check lint typecheck arch fix

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

# ── Docker-Varianten (wenn Tools nicht lokal installiert sind) ────────────────
check-docker:
	podman compose run --rm frontend npm run lint
	podman compose run --rm frontend npm run typecheck
	podman compose run --rm backend /app/.venv/bin/ruff check .
	podman compose run --rm backend /app/.venv/bin/mypy app/
	python scripts/arch-check.py
