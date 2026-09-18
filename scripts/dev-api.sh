#!/usr/bin/env bash
set -euo pipefail
# Local dev helper: starts API (requires backend/.venv + backend/.env).
cd "$(dirname "$0")/../backend"
source .venv/bin/activate
exec uvicorn app.main:app --reload --port "${PORT:-8000}"
