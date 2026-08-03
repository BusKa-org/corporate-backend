include .env
export

DOCKER := $(shell \
	if command -v docker-compose >/dev/null 2>&1; then \
		echo docker-compose; \
	elif docker compose version >/dev/null 2>&1; then \
		echo "docker compose"; \
	else \
		echo "ERROR: docker compose not found" >&2; exit 1; \
	fi \
)

# ==========================================
# Development
# ==========================================

.PHONY: run dev install install-dev

PYTHON := $(shell \
	if [ -n "$$VIRTUAL_ENV" ]; then \
		echo "python -m"; \
	elif command -v uv >/dev/null 2>&1; then \
		echo "uv run --"; \
	else \
		echo "python -m"; \
	fi \
)

install:
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		pip install -e .; \
	else \
		echo "WARNING: no virtual environment found, running with uv" >&2; \
		uv sync; \
	fi

run:
	$(DOCKER) -f infra/database.yml up -d db
	$(PYTHON) flask --app app run --host=0.0.0.0 --port=5000 --debug

# Espelha a produção: os jobs rodam em um processo separado da API, nunca
# dentro dela. Rode em outro terminal, junto com o `make run`.
scheduler:
	@export RUN_SCHEDULER=true; \
	if [ -n "$$VIRTUAL_ENV" ]; then \
		python -m app.scheduler_main; \
	else \
		uv run python -m app.scheduler_main; \
	fi

dev: run  # Alias for run

install-dev:
	uv sync --extra dev
	uv run pre-commit install

# ==========================================
# Database
# ==========================================

.PHONY: db-up db-down db-reset db-shell db-create seed migrate migrate-create migrate-history migrate-downgrade

db-up:
	$(DOCKER) -f infra/database.yml up -d db

db-down:
	$(DOCKER) -f infra/database.yml down

db-reset:
	$(DOCKER) -f infra/database.yml down --volumes
	$(DOCKER) -f infra/database.yml rm -f
	$(DOCKER) -f infra/database.yml up -d db
	@echo "Waiting for database to be ready..."
	@until docker exec buska_db psql -U buska_user -d buska_db -c "SELECT 1" > /dev/null 2>&1; do \
		echo "  still waiting..."; sleep 2; \
	done
	@echo "Database is ready."
	uv run alembic upgrade head
	@echo "Database reset complete. Run 'make seed' to populate data."

db-create:
	$(DOCKER) -f infra/database.yml up -d db
	@echo "Waiting for database to start..."
	sleep 5
	uv run alembic upgrade head

db-shell:
	PGPASSWORD=$${DB_PASSWORD:-buska_pass} psql -h $${DB_HOST:-localhost} -p $${DB_PORT:-5432} -U $${DB_USER:-buska_user} -d $${DB_NAME:-buska_db}

seed:
	uv run python seed.py

seed-sql:
	PGPASSWORD=$${DB_PASSWORD:-buska_pass} psql -h $${DB_HOST:-localhost} -p $${DB_PORT:-5432} -U $${DB_USER:-buska_user} -d $${DB_NAME:-buska_db} -f database/populate.sql

# Alembic migrations
migrate:
	uv run alembic upgrade head

migrate-create:
	@read -p "Migration message: " msg; \
	uv run alembic revision --autogenerate -m "$$msg"

migrate-history:
	uv run alembic history

migrate-downgrade:
	uv run alembic downgrade -1

migrate-current:
	uv run alembic current

# ==========================================
# Code Quality
# ==========================================

.PHONY: lint format typecheck check precommit

lint:
	uv run ruff check app/

format:
	uv run black app/ tests/
	uv run ruff check --fix app/

typecheck:
	uv run mypy app/

# Run all pre-commit checks (same as pre-commit hooks)
precommit:
	uv run black app/ tests/
	uv run ruff check --fix --exit-non-zero-on-fix app/ || true
	uv run mypy app/

check: lint typecheck  # Run all checks

# ==========================================
# Testing
# ==========================================
# Tests run against a dedicated "<DB_NAME>_test" database (or TEST_DATABASE_URI
# if set), auto-created with PostGIS on first run — never against the dev DB.

.PHONY: test test-cov test-unit test-integration

test:
	uv run pytest

test-cov:
	uv run pytest --cov=app --cov-report=term-missing

test-unit:
	uv run pytest tests/unit/

test-integration:
	uv run pytest tests/integration/

# ==========================================
# Documentation
# ==========================================

.PHONY: docs-openapi docs

docs-openapi:
	uv run -- flask --app app export-openapi
	@echo "OpenAPI spec exported to docs/openapi.json"

docs:
	@echo "Swagger UI available at: http://localhost:5000/docs"
	@echo "OpenAPI JSON available at: http://localhost:5000/openapi.json"
	uv run -- flask --app app run --debug

# ==========================================
# Cleanup
# ==========================================

.PHONY: clean

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

# ==========================================
# Help
# ==========================================

.PHONY: help

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Development:"
	@echo "  run / dev       Start the development server"
	@echo "  install         Install production dependencies"
	@echo "  install-dev     Install dev dependencies + pre-commit hooks"
	@echo ""
	@echo "Database:"
	@echo "  db-up           Start database container"
	@echo "  db-down         Stop database container"
	@echo "  db-reset        Reset database (drop + recreate via Alembic)"
	@echo "  db-create       Create database from scratch (Alembic)"
	@echo "  db-shell        Connect to database via psql"
	@echo "  seed            Seed data using seed.py"
	@echo "  seed-sql        Seed data using populate.sql"
	@echo ""
	@echo "Migrations (Alembic):"
	@echo "  migrate         Apply pending migrations"
	@echo "  migrate-create  Create a new migration (auto-generated)"
	@echo "  migrate-history Show migration history"
	@echo "  migrate-current Show current migration version"
	@echo "  migrate-downgrade  Rollback last migration"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint            Run ruff linter"
	@echo "  format          Format code with black + ruff"
	@echo "  typecheck       Run mypy type checker"
	@echo "  check           Run all checks (lint + typecheck)"
	@echo ""
	@echo "Testing:"
	@echo "  test            Run all tests"
	@echo "  test-cov        Run tests with coverage report"
	@echo "  test-unit       Run unit tests only"
	@echo ""
	@echo "Documentation:"
	@echo "  docs-openapi    Export OpenAPI spec to docs/openapi.json"
	@echo "  docs            Start server and show docs URLs"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean           Remove cache files"
	@echo ""
	@echo "Docker (production):"
	@echo "  docker-up       Start stack (banco preservado)"
	@echo "  docker-down     Stop stack (não apaga volume)"
	@echo "  docker-init-db  Extensão + migrações + seed (idempotente)"
	@echo "  docker-clean    Stop + apagar volumes e imagens (reset total)"

# Docker production targets
# docker-down NÃO usa --volumes: banco é preservado entre deploys.
# Use docker-clean apenas para reset total (apaga dados).

docker-build:
	docker build -t mebuska-corporate:latest .

docker-up:
	docker compose -f docker-compose.prod.yml --env-file .env.prod up -d

docker-down:
	docker compose -f docker-compose.prod.yml down

docker-init-db:
	@echo "Inicializa o banco prod (extensão + migrações + seed). Idempotente."
	@test -f .env.prod || (echo "Crie .env.prod com DB_USER, DB_PASSWORD, DB_NAME" && exit 1)
	export $$(grep -v '^#' .env.prod | xargs) && export DB_HOST=localhost && export DB_PORT=5432 && bash scripts/init-db.sh

docker-logs:
	docker compose -f docker-compose.prod.yml logs -f

docker-rebuild:
	docker compose -f docker-compose.prod.yml down
	docker build -t mebuska-corporate:latest .
	docker compose -f docker-compose.prod.yml up -d

docker-clean:
	docker compose -f docker-compose.prod.yml down --volumes --rmi all
