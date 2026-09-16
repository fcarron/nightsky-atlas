PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
PY := $(BIN)/python

.PHONY: setup test lint check clean

setup: $(VENV)/bin/activate

$(VENV)/bin/activate: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]"
	@touch $(VENV)/bin/activate

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

check: lint test

clean:
	rm -rf $(VENV) build dist .pytest_cache .ruff_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
