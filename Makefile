.PHONY: lint fmt check

# Check everything — same rules as CI, all at once
check:
	ruff check .
	black --check --diff .

# Auto-fix what can be fixed
resolve:
	black .
	ruff check . --fix
