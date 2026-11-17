PY ?= python
.PHONY: qc lint types test fmt lock
qc: lint types test
lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .
types:
	$(PY) -m pyright
test:
	$(PY) -m pytest
fmt:
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .
lock:
	$(PY) -m uv lock
