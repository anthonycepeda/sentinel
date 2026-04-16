-include .env
export

.DEFAULT_GOAL := help
.PHONY: help install run test lint fmt collect clean

help:
	@echo "install  — uv sync"
	@echo "run      — start API server on :8000 (hot-reload)"
	@echo "test     — run full test suite"
	@echo "lint     — ruff check + format check"
	@echo "fmt      — ruff auto-fix and format"
	@echo "collect  — POST /collect to trigger a manual telemetry pull"
	@echo "clean    — remove .venv, caches, sentinel.db"

install:
	uv sync

run:
	uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

collect:
	curl -s -X POST http://localhost:8000/collect | python3 -m json.tool

clean:
	rm -rf .venv .pytest_cache .ruff_cache sentinel.db
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
