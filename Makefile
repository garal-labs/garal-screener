.PHONY: check typecheck resolve

PYTHON = .venv/bin/python

# Check everything — same rules as CI, all at once
check:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m black --check --diff .
	$(PYTHON) -m mypy . --ignore-missing-imports --no-error-summary

# Type check only
typecheck:
	$(PYTHON) -m mypy . --ignore-missing-imports --no-error-summary

# Auto-fix what can be fixed
resolve:
	$(PYTHON) -m black .
	$(PYTHON) -m ruff check . --fix
