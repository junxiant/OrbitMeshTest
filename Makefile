.PHONY: setup ingest chat test eval all

PYTHON ?= python

setup:
	@echo "Installing dependencies..."
	$(PYTHON) -m pip install -r requirements.txt

ingest:
	@echo "Running corpus ingestion..."
	$(PYTHON) -m src.ingestion.indexer

chat:
	@echo "Starting interactive chat CLI..."
	$(PYTHON) -m src.cli.interactive

test:
	@echo "Running automated test suite..."
	$(PYTHON) -m pytest tests/

eval:
	@echo "Running evaluation benchmark..."
	$(PYTHON) eval/runner.py
