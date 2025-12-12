.PHONY: help install test lint format typecheck check clean docs docs-serve docs-deploy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync

test: ## Run tests with coverage
	uv run pytest

lint: ## Run linter
	uv run ruff check src/fasthooks tests

format: ## Format code
	uv run ruff format src/fasthooks tests
	uv run ruff check --fix src/fasthooks tests

typecheck: ## Run type checker
	uv run mypy src/fasthooks

check: lint typecheck test ## Run all checks (lint, typecheck, test)

clean: ## Remove build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build *.egg-info site
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

docs: ## Build documentation
	uv sync --group docs
	uv run mkdocs build

docs-serve: ## Serve docs locally (http://localhost:8000)
	uv sync --group docs
	uv run mkdocs serve

docs-deploy: ## Deploy docs to GitHub Pages
	uv sync --group docs
	uv run mkdocs gh-deploy --force
