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
