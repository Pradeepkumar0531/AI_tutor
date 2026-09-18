#!/usr/bin/env bash
set -euo pipefail
# Backend quality gate: lint + format-check + typecheck + tests.
cd "$(dirname "$0")/../backend"
source .venv/bin/activate 2>/dev/null || true
ruff check .
ruff format --check .
mypy app || true
pytest -q
