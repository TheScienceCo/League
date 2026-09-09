# AoE2 Lab — common tasks.
#
#   make up        bring the whole stack up in Docker
#   make demo      up, then analyse a replay with `make analyse REC=...`
#   make test      run the backend suite
#
# Targets that talk to the database work against Docker Compose by default.

SHELL := /bin/bash
COMPOSE := docker compose
BACKEND := cd backend &&
FRONTEND := cd frontend &&

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# --- Docker ----------------------------------------------------------------

.PHONY: up
up: .env ## Build and start the full stack
	$(COMPOSE) up --build -d
	@echo "API  -> http://localhost:8000/docs"
	@echo "Web  -> http://localhost:3000"

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and delete its volumes (destroys all data)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail the api and worker logs
	$(COMPOSE) logs -f api worker

.env:
	cp .env.example .env
	@echo "Created .env from .env.example"

# --- Data ------------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply database migrations
	$(COMPOSE) exec api alembic upgrade head

.PHONY: analyse
analyse: ## Analyse a replay: make analyse REC=path/to/game.aoe2record
	curl -sS -F file=@$(REC) localhost:$(or $(API_PORT),8000)/api/v1/replays | python3 -m json.tool

.PHONY: demo
demo: up ## Bring the whole stack up and wait for it to be healthy
	@echo "Waiting for the API to become healthy..."
	@until [ "$$($(COMPOSE) ps -q api | xargs docker inspect -f '{{.State.Health.Status}}')" = "healthy" ]; do sleep 2; done
	@echo "Stack is up. Open http://localhost:3000 and upload an .aoe2record file."

# --- Backend ---------------------------------------------------------------

.PHONY: install
install: ## Create the backend virtualenv and install dependencies
	$(BACKEND) python -m venv .venv && .venv/bin/pip install -e ".[dev]"
	$(FRONTEND) npm ci

.PHONY: test
test: ## Run the fast backend suite
	$(BACKEND) .venv/bin/python -m pytest -q

.PHONY: lint
lint: ## Lint and type-check the backend, type-check the frontend
	$(BACKEND) .venv/bin/ruff check app tests
	$(BACKEND) .venv/bin/ruff format --check app tests
	$(BACKEND) .venv/bin/mypy app
	$(FRONTEND) npx tsc --noEmit

.PHONY: format
format: ## Auto-format and auto-fix
	$(BACKEND) .venv/bin/ruff check app tests --fix
	$(BACKEND) .venv/bin/ruff format app tests

.PHONY: api
api: ## Run the API locally (expects Postgres on localhost:5432)
	$(BACKEND) .venv/bin/uvicorn app.main:app --reload --port 8000

.PHONY: web
web: ## Run the frontend locally against a local API
	$(FRONTEND) API_INTERNAL_URL=http://localhost:8000 npm run dev
