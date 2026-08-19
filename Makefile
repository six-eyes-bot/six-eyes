# The Desk — one target to provision, one to verify.
#
# `test` is the name CI's required status check looks for. Renaming the CI job
# or this target blocks every merge; see .github/workflows/ci.yml.

PY      ?= python3.11
VENV    ?= .venv
BIN      = $(VENV)/bin

.DEFAULT_GOAL := help

.PHONY: help setup lock test lint type unit clean

help:
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

setup: ## create .venv on Python 3.11 and install from the lockfile
	@command -v $(PY) >/dev/null || { echo "$(PY) not found. Floor is 3.11, ceiling <3.15 (litellm)."; exit 1; }
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	@if [ -f requirements.lock ]; then \
		echo "installing from requirements.lock (hash-checked)"; \
		$(BIN)/pip install -q --require-hashes -r requirements.lock; \
	else \
		echo "no requirements.lock yet — run 'make lock' first"; exit 1; \
	fi
	$(BIN)/pip install -q -e . --no-deps
	@echo "setup ok — $$($(BIN)/python --version)"

lock: ## regenerate requirements.lock from pyproject (hashes included)
	$(PY) -m venv $(VENV) 2>/dev/null || true
	$(BIN)/pip install -q --upgrade pip pip-tools
	$(BIN)/pip-compile --quiet --generate-hashes --strip-extras \
		--extra dev --output-file requirements.lock pyproject.toml
	@echo "locked $$(grep -c '^[a-zA-Z]' requirements.lock) distributions"

lint: ## ruff
	$(BIN)/ruff check .

type: ## mypy
	$(BIN)/mypy

unit: ## pytest
	$(BIN)/pytest -q

test: lint type unit ## lint + type + unit, in that order
	@echo "make test: all green"

clean:
	rm -rf $(VENV) .pytest_cache .mypy_cache .ruff_cache
