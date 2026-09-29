.PHONY: sync lint format typecheck test ci bench

sync:
	uv sync

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy src/evalflow

test:
	uv run pytest

ci: lint typecheck test

bench:
	uv run evalflow bench \
		--model configs/v2.yaml \
		--baseline-model configs/v1.yaml \
		--scenarios scenarios/ \
		--workers 4 \
		--repeats 3
