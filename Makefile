# D3 Brand-Safe Creative and Content Studio — developer tasks.
#
# The gate (lint + format + types + tests + eval) runs on the local profile with the
# [dev] extra only (no google-cloud-*), matching CI. Override PROFILE=gcp for the managed
# stack, or PROFILE=onprem for the fail-fast migration target.

PY ?= python3.14
VENV ?= .venv
BIN := $(VENV)/bin
PROFILE ?= local

API_APP := creative_studio.api.app:app
API_HOST ?= 127.0.0.1  # no-auth local dev binds loopback; override deliberately
API_PORT ?= 8102
UI_DIR := ui
DEMO_PORT ?= 8112
TF_DIR := infra/terraform

export MKT_CREATIVE_PROFILE := $(PROFILE)

.PHONY: venv install install-gcp lint format typecheck test eval gate \
        ui-install ui-check demo demo-server demo-selftest smoke-local run-api run-ui tf-validate tf-plan clean

venv:
	$(PY) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip

install: venv ## Install the package + dev tooling (NO GCP SDK — local/onprem profile).
	$(BIN)/python -m pip install -e ".[dev]"

install-gcp: ## Install with the managed-stack extra (google-genai, discoveryengine, ...).
	$(BIN)/python -m pip install -e ".[gcp,dev]"

lint:
	$(BIN)/ruff check src tests

format:
	$(BIN)/ruff format --check src tests

typecheck:
	$(BIN)/mypy src

test:
	$(BIN)/pytest -m "not integration" -q

eval:
	$(BIN)/python eval/run_eval.py

# The full gate, green before any change lands.
portability:
	PYTHONPATH=src $(BIN)/python scripts/portability_demo.py

plugin: ## Render the Agent Plugins 1.0.0 directory from this repo's own declarations.
	python scripts/render_plugin.py --dest dist/plugin

mcp-serve: ## Serve the governed tool catalog over MCP 2026-07-28 (stdio; needs [gcp]).
	python -m creative_studio.mcp

gate: lint format typecheck test eval demo-selftest portability plugin

ui-install: ## Install the console's locked dependencies (proves package-lock.json still resolves).
	npm ci --prefix $(UI_DIR)

ui-check: ## The console's gate. `assert-hydratable` runs LAST, against the build just made.
	npm --prefix $(UI_DIR) run lint
	npm --prefix $(UI_DIR) test
	NEXT_TELEMETRY_DISABLED=1 npm --prefix $(UI_DIR) run build
	npm --prefix $(UI_DIR) run assert-hydratable

demo: ## Offline demo: run the creative flow + render the static audit-first HTML (scripts/out).
	MKT_CREATIVE_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo.py
	MKT_CREATIVE_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/render_result_ui.py scripts/out

demo-server: ## Live, presenter-controlled offline demo server on :$(DEMO_PORT).
	MKT_CREATIVE_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo_server.py --port $(DEMO_PORT)

demo-selftest:
	MKT_CREATIVE_PROFILE=local PYTHONPATH=src $(BIN)/python scripts/demo_selftest.py

smoke-local: ## End-to-end offline smoke: generate brand-safe creative under the local profile.
	MKT_CREATIVE_PROFILE=local $(BIN)/mkt-creative generate "high-yield savings" -m SG -v banking -o "4.10% p.a."

run-api: ## Run the real FastAPI service on :$(API_PORT) (PROFILE=$(PROFILE)).
	$(BIN)/uvicorn $(API_APP) --host $(API_HOST) --port $(API_PORT)

run-ui: ## Run the thin Next.js console (dev server); set NEXT_PUBLIC_API_BASE to the API.
	cd $(UI_DIR) && npm install && npm run dev

tf-plan: ## Terraform plan for the pinned Singapore region (residency/CMEK/VPC-SC posture).
	cd $(TF_DIR) && terraform init -backend=false && terraform plan

tf-validate:
	cd $(TF_DIR) && terraform fmt -check -recursive && terraform init -backend=false -input=false && terraform validate

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache .mypy_cache scripts/out
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
