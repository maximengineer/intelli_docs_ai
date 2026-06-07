SHELL := /usr/bin/env bash

BACKEND_PORT ?= 7777
FRONTEND_PORT ?= 9999
LIVE_EMBEDDING_BACKEND ?= hash
LIVE_REQUIRE_PROVIDER_EMBEDDINGS ?= false

.DEFAULT_GOAL := help

.PHONY: help build up up-alt down restart ps logs logs-backend logs-worker logs-frontend test eval alembic-sql live-test live-test-embeddings config config-all clean

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
	@echo "  make live-test           Run opt-in provider-backed smoke test"
	@echo "  make live-test-embeddings Run live smoke requiring provider embeddings"
	@echo "  make config              Validate default Compose config"
	@echo "  make config-all          Validate test and live-test profiles"
	@echo ""
	@echo "Variables:"
	@echo "  BACKEND_PORT=18000 FRONTEND_PORT=18501 make up"
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
	docker compose --profile test run --rm tests

eval:
	docker compose --profile test run --rm tests python scripts/run_evaluation.py

alembic-sql:
	docker compose --profile test run --rm tests alembic upgrade head --sql

live-test:
	LIVE_EMBEDDING_BACKEND=$(LIVE_EMBEDDING_BACKEND) LIVE_REQUIRE_PROVIDER_EMBEDDINGS=$(LIVE_REQUIRE_PROVIDER_EMBEDDINGS) docker compose --profile live-test run --rm live-tests

live-test-embeddings:
	LIVE_EMBEDDING_BACKEND=openrouter LIVE_REQUIRE_PROVIDER_EMBEDDINGS=true docker compose --profile live-test run --rm live-tests

config:
	docker compose config --quiet

config-all:
	docker compose --profile test --profile live-test config --quiet

clean:
	docker compose down --remove-orphans
