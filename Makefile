PY ?= python3
SEED ?= 1999

.PHONY: data validate test spike

data:
	$(PY) authoring/build_archive.py --seed $(SEED)

validate:
	$(PY) authoring/validate_dataset.py --seed $(SEED)

test:
	$(PY) -m pytest -q

spike:
	$(PY) scripts/spike.py

.PHONY: web serve demo replay
web:
	cd web && npm ci && npm run build

serve: web           ## the game, with a real local model (Ollama)
	$(PY) -m uvicorn lastwitness.app:app --app-dir server --port 8000

demo: web            ## click through without any model (echo mode quotes sentences, no AI)
	LW_MODEL=echo $(PY) -m uvicorn lastwitness.app:app --app-dir server --port 8000

replay:              ## record a real run for the static GitHub Pages version
	$(PY) scripts/record_replay.py --model $${LW_MODEL:-gemma4:e4b}
