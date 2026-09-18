#!/usr/bin/env bash
set -euo pipefail
# Local dev helper: starts Celery worker (requires backend/.venv + Redis URL for real jobs).
cd "$(dirname "$0")/../backend"
source .venv/bin/activate
exec celery -A app.jobs.worker.celery worker --loglevel=info
