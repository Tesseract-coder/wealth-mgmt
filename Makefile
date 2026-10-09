SHELL := /bin/bash
-include .env
BACKEND_PORT ?= 8000
UV ?= $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)
# Load nvm if it is installed, so `node`/`npm` resolve in non-interactive shells.
NODE := export NVM_DIR="$(HOME)/.nvm"; [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" >/dev/null;

.PHONY: help setup dev dev-backend dev-frontend test test-backend test-frontend lint fmt docker-up docker-down clean

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-15s %s\n", $$1, $$2}'

setup:  ## Install backend (uv, Python 3.12) and frontend (npm) dependencies
	cd backend && $(UV) sync
	$(NODE) cd frontend && npm ci
	@[ -f .env ] || (cp .env.example .env && echo "Created .env from .env.example")

dev:  ## Run backend (:8000) and frontend (:5173) together; Ctrl-C stops both
	@$(MAKE) -j2 --no-print-directory dev-backend dev-frontend

dev-backend:
	cd backend && $(UV) run uvicorn app.main:app --reload --host 127.0.0.1 --port $(BACKEND_PORT)

dev-frontend:
	$(NODE) cd frontend && VITE_BACKEND_URL=http://localhost:$(BACKEND_PORT) npm run dev

test: test-backend test-frontend  ## Run all tests

test-backend:
	cd backend && $(UV) run pytest

test-frontend:
	$(NODE) cd frontend && npm test

lint:  ## Lint + type-check backend and frontend
	cd backend && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy app
	$(NODE) cd frontend && npm run typecheck

fmt:  ## Auto-format backend
	cd backend && $(UV) run ruff check --fix . && $(UV) run ruff format .

docker-up:  ## Run everything in Docker
	docker compose up --build

docker-down:
	docker compose down

clean:  ## Remove build artifacts (keeps your database)
	rm -rf frontend/dist backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
