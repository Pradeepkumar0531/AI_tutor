#!/usr/bin/env bash
# Single-service entrypoint: migrate, then run API + Celery worker together.
# Either process dying exits the container so the host restarts a healthy one.
set -euo pipefail

cd /srv/backend
: "${PORT:=7860}"

echo "[boot] running database migrations..."
alembic upgrade head

echo "[boot] starting celery worker (solo pool, concurrency 1)..."
celery -A app.jobs.worker.celery worker --pool=solo --concurrency=1 --loglevel=info &
WORKER_PID=$!

echo "[boot] starting API on port ${PORT}..."
uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" &
API_PID=$!

terminate() {
  kill "${WORKER_PID}" "${API_PID}" 2>/dev/null || true
}
trap terminate SIGTERM SIGINT

# Exit when the first process exits; shut the other one down.
wait -n
STATUS=$?
terminate
wait 2>/dev/null || true
exit "${STATUS}"
