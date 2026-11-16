PY ?= python
.PHONY: qc lint types test fmt lock
qc: lint types test
lint:
	$(PY) -m ruff check .
types:
	$(PY) -m pyright
test:
	$(PY) -m pytest
fmt:
	$(PY) -m ruff check --fix .
lock:
	$(PY) -m uv lock
