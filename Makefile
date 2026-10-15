PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
PY := $(BIN)/python

.PHONY: setup test test-fast lint check clean

setup: $(VENV)/bin/activate

$(VENV)/bin/activate: pyproject.toml
	$(PYTHON) -m venv --system-site-packages $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	@touch $(VENV)/bin/activate

test:
	$(PY) -m pytest

test-fast:
	$(PY) -m pytest -m "not slow and not integration"

lint:
	$(PY) -m ruff check .

check: lint test

clean:
	rm -rf $(VENV) build dist .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
