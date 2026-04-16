.PHONY: install run test lint format collect clean

install:
	uv sync

run:
	uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

test:
	uv run pytest -v

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

collect:
	curl -s -X POST http://localhost:8000/collect | python3 -m json.tool

clean:
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache sentinel.db
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
