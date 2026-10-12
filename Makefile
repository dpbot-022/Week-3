VENV_BIN := $(shell if [ -d .venv ]; then echo ./.venv/bin; else echo ""; fi)
PYTHON ?= $(if $(VENV_BIN),$(VENV_BIN)/python,python3)
PYTEST ?= $(if $(VENV_BIN),$(VENV_BIN)/pytest,pytest)
UVICORN ?= $(if $(VENV_BIN),$(VENV_BIN)/uvicorn,uvicorn)

.PHONY: test eval check-eval-stale seed run

test:
	$(PYTEST)

eval:
	$(PYTHON) scripts/run_evals.py

seed:
	$(PYTHON) scripts/seed_demo_data.py

check-eval-stale:
	$(PYTHON) -c "from pathlib import Path; import json; report = json.loads(Path('reports/latest_eval.json').read_text()); readme = Path('README.md').read_text(); assert report['dataset_hash'][:12] in readme, 'README.md evaluation table is stale! Run make eval';"

run:
	$(UVICORN) src.api.main:app --host 0.0.0.0 --port 8001 --reload
