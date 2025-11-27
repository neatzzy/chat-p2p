PYTEST := $(shell [ -x venv/bin/pytest ] && echo "venv/bin/pytest" || echo "python -m pytest")
PY := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null || echo python)
TEST_ARGS := --maxfail=1 -q --cov=src --cov-report=term-missing

.PHONY: test coverage install-reqs

test:
	$(PYTEST) $(TEST_ARGS)

coverage:
	$(PYTEST) $(TEST_ARGS)

install-reqs:
	$(PY) -m pip install -r requirements.txt
