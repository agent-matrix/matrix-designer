# Matrix Designer — the Brain of the Matrix ecosystem.
# Quickstart:  make install  &&  make test  &&  make run
.DEFAULT_GOAL := help
PY ?= python3
PORT ?= 8077
HOST ?= 0.0.0.0

.PHONY: help install install-all test run run-mcp blueprints dev lint clean version

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install Matrix Designer + the service & MCP extras (editable)
	$(PY) -m pip install -e ".[service,mcp,dev]"

install-all: ## Install everything, incl. the agentic backends (CrewAI + LangGraph)
	$(PY) -m pip install -e ".[service,mcp,agentic,langgraph,dev]"

test: ## Run the test suite
	$(PY) -m pytest -q

run: ## Start the HTTP service (FastAPI) — the brain over HTTP for Matrix Builder
	@echo "Matrix Designer service → http://$(HOST):$(PORT)  (POST /design/{blueprints,refine,bundle,review}, GET /healthz)"
	MATRIX_DESIGNER_PORT=$(PORT) $(PY) -m matrix_designer.service

run-mcp: ## Start the stdio MCP server (matrix-designer)
	$(PY) -m matrix_designer.mcp_server

blueprints: ## Demo: design 3 blueprints for an idea  (make blueprints IDEA="...")
	mdesign blueprints --idea "$(or $(IDEA),A Hello World static website)"

dev: ## Run the HTTP service with auto-reload (development)
	MATRIX_DESIGNER_PORT=$(PORT) uvicorn 'matrix_designer.service:build_app' --factory --reload --host $(HOST) --port $(PORT)

lint: ## Lint with ruff (if installed)
	-$(PY) -m ruff check src tests

version: ## Print the version
	@cat VERSION

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache **/__pycache__ src/*.egg-info build dist
