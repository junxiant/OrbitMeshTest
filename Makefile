.PHONY: setup ingest chat test eval record-fixtures eval-live all

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
	LLM_MODE=mock $(PYTHON) -m pytest tests/

eval:
	@echo "Running evaluation benchmark..."
	$(PYTHON) eval/runner.py

record-fixtures:
	@echo "Recording evaluation fixtures..."
	LLM_MODE=record $(PYTHON) eval/runner.py

eval-live:
	@echo "Running live evaluation..."
	LLM_MODE=live $(PYTHON) eval/runner.py

all:setup ingest test eval
