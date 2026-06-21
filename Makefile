SHELL := /usr/bin/env bash

BACKEND_PORT ?= 7777
FRONTEND_PORT ?= 9999
LIVE_EMBEDDING_BACKEND ?= hash
LIVE_REQUIRE_PROVIDER_EMBEDDINGS ?= false
LIVE_TEST_TIMEOUT_SECONDS ?= 300
KEEP_STACK ?= false

.DEFAULT_GOAL := help

.PHONY: help build up up-alt down restart ps logs logs-backend logs-worker logs-frontend test eval alembic-sql alembic-integration-test celery-integration-test live-test live-test-embeddings _live-test config config-all clean

help:
	@echo "IntelliDocs AI Docker workflow"
	@echo ""
	@echo "App:"
	@echo "  make build               Build backend, worker and frontend images"
	@echo "  make up                  Start the full app stack"
	@echo "  make up-alt              Start using BACKEND_PORT=18000 FRONTEND_PORT=18501"
	@echo "  make down                Stop and remove stack containers"
	@echo "  make restart             Restart the full app stack"
	@echo "  make ps                  Show service status"
	@echo "  make logs                Tail all service logs"
	@echo "  make logs-backend        Tail backend logs"
	@echo "  make logs-worker         Tail worker logs"
	@echo "  make logs-frontend       Tail frontend logs"
	@echo ""
	@echo "Verification:"
	@echo "  make test                Run deterministic offline tests in Docker"
	@echo "  make eval                Run offline evaluation in Docker"
	@echo "  make alembic-sql         Generate Alembic SQL in Docker"
	@echo "  make alembic-integration-test Apply migrations to isolated Postgres and validate schema"
	@echo "  make celery-integration-test Run isolated Celery/Postgres success, failure and restart tests"
	@echo "  make live-test           Run opt-in provider-backed smoke test"
	@echo "  make live-test-embeddings Run live smoke requiring provider embeddings"
	@echo "  make config              Validate default Compose config"
	@echo "  make config-all          Validate test and live-test profiles"
	@echo ""
	@echo "Variables:"
	@echo "  BACKEND_PORT=18000 FRONTEND_PORT=18501 make up"
	@echo "  KEEP_STACK=true make celery-integration-test"
	@echo "  LIVE_TEST_TIMEOUT_SECONDS=300 make live-test"
	@echo "  LIVE_EMBEDDING_BACKEND=openrouter LIVE_REQUIRE_PROVIDER_EMBEDDINGS=true make live-test"

build:
	docker compose build backend worker frontend

up:
	BACKEND_PORT=$(BACKEND_PORT) FRONTEND_PORT=$(FRONTEND_PORT) docker compose up -d --build backend worker frontend

up-alt:
	BACKEND_PORT=18000 FRONTEND_PORT=18501 docker compose up -d --build backend worker frontend

down:
	docker compose down

restart: down up

ps:
	docker compose ps

logs:
	docker compose logs -f

logs-backend:
	docker compose logs -f backend

logs-worker:
	docker compose logs -f worker

logs-frontend:
	docker compose logs -f frontend

test:
	docker compose --profile test run --build --rm tests

eval:
	docker compose --profile test run --build --rm tests python scripts/run_evaluation.py

alembic-sql:
	docker compose --profile test run --build --rm tests alembic upgrade head --sql

alembic-integration-test:
	set -euo pipefail; \
	migration_project="intellidocs-alembic-$$$$"; \
	trap 'docker compose -p "$$migration_project" down -v --rmi local --remove-orphans' EXIT; \
	docker compose -p "$$migration_project" up -d --wait postgres; \
	docker compose -p "$$migration_project" --profile test build tests; \
	docker compose -p "$$migration_project" --profile test run --rm \
		-e DATABASE_URL=postgresql://intellidocs:intellidocs@postgres:5432/intellidocs \
		-e ALEMBIC_TEST_DATABASE_URL=postgresql://intellidocs:intellidocs@postgres:5432/intellidocs \
		-e RUN_ALEMBIC_INTEGRATION=1 \
		tests sh -ec 'alembic upgrade head && pytest backend/tests/integration/test_alembic_migrations.py'

celery-integration-test:
	set -euo pipefail; \
	integration_project="intellidocs-celery-$$$$"; \
	integration_run="$$$$-$$(date +%s)"; \
	cleanup() { \
		status=$$?; \
		if [ "$$status" -ne 0 ]; then \
			docker compose -p "$$integration_project" logs --no-color postgres redis backend worker || true; \
		fi; \
		if [ "$(KEEP_STACK)" != "true" ]; then \
			docker compose -p "$$integration_project" down -v --rmi local --remove-orphans || true; \
		else \
			echo "Preserving Compose project $$integration_project"; \
		fi; \
		exit "$$status"; \
	}; \
	trap cleanup EXIT; \
	export ENABLE_LLM=false EMBEDDING_BACKEND=hash DOCUMENT_PROCESSING_BACKEND=celery BACKEND_PORT=0 FRONTEND_PORT=0; \
	echo "Using isolated Compose project $$integration_project"; \
	docker compose -p "$$integration_project" up -d --build --wait backend worker; \
	docker compose -p "$$integration_project" --profile test build tests; \
	docker compose -p "$$integration_project" --profile test run --rm \
		-e RUN_CELERY_INTEGRATION=1 \
		-e CELERY_INTEGRATION_RUN_ID="$$integration_run" \
		-e INTELLIDOCS_API_URL=http://backend:8000 \
		tests pytest \
			backend/tests/integration/test_celery_document_processing.py::test_celery_document_processing_round_trip \
			backend/tests/integration/test_celery_document_processing.py::test_celery_document_failure_is_durable; \
	docker compose -p "$$integration_project" restart backend; \
	docker compose -p "$$integration_project" up -d --wait backend; \
	docker compose -p "$$integration_project" --profile test run --rm \
		-e RUN_CELERY_INTEGRATION=1 \
		-e CELERY_INTEGRATION_RUN_ID="$$integration_run" \
		-e INTELLIDOCS_API_URL=http://backend:8000 \
		tests pytest \
			backend/tests/integration/test_celery_document_processing.py::test_completed_document_survives_backend_restart

live-test: _live-test

live-test-embeddings: LIVE_EMBEDDING_BACKEND = openrouter
live-test-embeddings: LIVE_REQUIRE_PROVIDER_EMBEDDINGS = true
live-test-embeddings: _live-test

_live-test:
	set -euo pipefail; \
	live_project="intellidocs-live-$$$$"; \
	cleanup() { \
		status=$$?; \
		if [ "$$status" -ne 0 ]; then \
			docker compose -p "$$live_project" logs --no-color postgres backend || true; \
		fi; \
		if [ "$(KEEP_STACK)" != "true" ]; then \
			docker compose -p "$$live_project" --profile live-test down -v --rmi local --remove-orphans || true; \
		else \
			echo "Preserving Compose project $$live_project"; \
		fi; \
		exit "$$status"; \
	}; \
	trap cleanup EXIT; \
	export ENABLE_LLM=true STRICT_PROVIDER_MODE=true; \
	export EMBEDDING_BACKEND="$(LIVE_EMBEDDING_BACKEND)"; \
	export LIVE_REQUIRE_PROVIDER_EMBEDDINGS="$(LIVE_REQUIRE_PROVIDER_EMBEDDINGS)"; \
	export DOCUMENT_PROCESSING_BACKEND=thread BACKEND_PORT=0 FRONTEND_PORT=0; \
	echo "Using isolated Compose project $$live_project"; \
	docker compose -p "$$live_project" --profile live-test build backend live-tests; \
	docker compose -p "$$live_project" --profile live-test up -d --wait backend; \
	timeout --foreground "$(LIVE_TEST_TIMEOUT_SECONDS)s" \
		docker compose -p "$$live_project" --profile live-test run --no-deps --rm live-tests

config:
	docker compose config --quiet

config-all:
	docker compose --profile test --profile live-test config --quiet

clean:
	docker compose down --remove-orphans
