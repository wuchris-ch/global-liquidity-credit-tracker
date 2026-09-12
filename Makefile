.PHONY: install test smoke smoke-live export update dev frontend-build

install:        ## Install Python package (editable) + dev tools
	pip install -e ".[dev]"

test:           ## Run the calculation test suite (offline, no API keys)
	python -m pytest tests/

smoke:          ## Offline smoke checks: config, numerics, local artifacts
	python scripts/smoke.py

smoke-live:     ## Smoke checks + validate the published GitHub Pages data
	python scripts/smoke.py --live

update:         ## Fetch fresh data and compute all indices (needs FRED_API_KEY)
	python scripts/update_data.py

export:         ## Export curated data to static JSON under data/export/latest
	python scripts/export_to_json.py --output data/export/latest

dev:            ## Run the local FastAPI backend
	uvicorn src.api:app --reload --port 8000

frontend-build: ## Build the Next.js frontend
	cd frontend && npm run build

.PHONY: research-setup research-demo research-api research-types research-test research-benchmark
research-setup:
	uv sync --locked --extra dev
	cd frontend && npm ci

research-demo:
	uv run macro-research demo

research-api:
	uv run macro-research serve

research-types:
	uv run python -m scripts.research_openapi
	uv run python -m scripts.research_types

research-test:
	uv run pytest tests/research
	uv run macro-research evaluate

research-benchmark:
	uv run python -m scripts.research_benchmark
