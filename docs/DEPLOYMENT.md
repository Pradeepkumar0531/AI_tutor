# Deployment (overview + runbook)

Topology (modular monolith, no new infra):

- Frontend → Vercel (static build `npm run build` → `dist/`), `VITE_API_BASE_URL` → API origin.
- Backend → any Python host (e.g. Render/Fly): `uvicorn app.main:app`, env from `backend/.env.example`.
- Worker → same image + `celery -A app.jobs.worker.celery worker`; Flower optional (`--port=5555`).
- Database → Neon (`DATABASE_URL`); run `alembic upgrade head`. Queue → Upstash Redis.

Deployment configs in the repo (no secrets inside):

- `frontend/vercel.json` — build/output plus the SPA rewrite (`/(.*)` →
  `/index.html`) that client-side routing requires; without it deep links 404.
  In the Vercel dashboard set `VITE_API_BASE_URL` to the API origin.
- `render.yaml` — Render blueprint for `alc-api` (web + `alembic upgrade head`
  pre-deploy + `/api/v1/health` check) and `alc-worker` (same image, Celery);
  all secret values are `sync: false` dashboard entries. Frontend stays on
  Vercel per the topology above.
- `Dockerfile` (+ `scripts/start-single.sh`, `backend/requirements.txt`) —
  single-container image (API + Celery solo worker, migrations on boot) for
  hosts that run one container: Hugging Face Spaces (Docker SDK, CPU Basic
  free) or any Docker host. `scripts/push-space.sh` pushes a clean deploy
  mirror to a Space. Secrets are Space secrets, never in the repo.

## Hugging Face Spaces (free backend)

Prerequisites: HF account, Space created as **Docker SDK** on **CPU Basic**
(free: 2 vCPU / 16 GB), write-role access token (avatar → Settings →
Access Tokens → New token, role `write`).

1. Commit everything (`scripts/push-space.sh` refuses a dirty tree — what is
   committed is what deploys).
2. Space → Settings → **Variables and secrets**, add (secret unless noted):
   `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`,
   `JWT_SECRET_KEY` (random ≥32 chars, e.g. `openssl rand -hex 32`),
   `CORS_ORIGINS` (`https://<user>-<space>.hf.space,https://<vercel-app>.vercel.app`),
   `ADMIN_EMAILS`, `GROQ_API_KEY`, `GOOGLE_API_KEY`, `STORAGE_BACKEND=neon`
   (variable) + `NEON_STORAGE_*`. Startup refuses dev defaults — missing or
   placeholder values fail fast with a clear error, by design.
3. Deploy: `HF_TOKEN=hf_xxx ./scripts/push-space.sh <hf-username> <space-name>`
   (repeat after each commit to redeploy). Watch the build log on the Space page.
4. Verify: `GET https://<user>-<space>.hf.space/api/v1/health` →
   `{"status":"ok",...}`. Migrations run automatically at container boot.
5. Point the frontend at it: Vercel → `VITE_API_BASE_URL` = the Space origin,
   redeploy frontend. Then register, upload the fixture PDF, wait for READY,
   generate a quiz — the full loop proves API + worker + queue.
6. Limits: free Spaces **sleep when idle** (wake on visit; queued uploads
   process after wake-up — Redis redelivers unacked jobs, nothing is lost).
   Demo-grade, not always-on production.

## Start commands (verified, not invented)

| Component | Command | CWD |
|---|---|---|
| Backend API | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | `backend/` |
| Celery worker | `celery -A app.jobs.worker.celery worker --loglevel=info` | `backend/` |
| DB migrations | `alembic upgrade head` | `backend/` |
| Frontend build | `npm run build` | `frontend/` |
| Frontend preview | `npm run preview` | `frontend/` |
| Full-loop smoke | `TEST_FAKE_AI=true .venv/bin/python ../scripts/smoke_test.py` | `backend/` |

## Production environment (required)

- `APP_ENV=production`, `DEBUG=false`.
- `DATABASE_URL` (Neon), `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` (Upstash Redis).
- `JWT_SECRET_KEY`: random, ≥32 chars (startup refuses dev defaults).
- `CORS_ORIGINS`: exact frontend origin(s) — startup refuses dev defaults.
- `ADMIN_EMAILS`: comma-separated admin bootstrap emails (promoted on
  register/login; the only privilege path — keep secret, no public endpoint).
- After deploy: run the evaluation suite from Admin → AI evaluation (or
  `pytest tests/test_ai_evaluation.py`) to confirm the learning loop before
  announcing availability.
- `STORAGE_BACKEND=neon` + `NEON_STORAGE_ENDPOINT`/`NEON_STORAGE_REGION`/
  `NEON_STORAGE_ACCESS_KEY_ID`/`NEON_STORAGE_SECRET_ACCESS_KEY`/
  `NEON_STORAGE_BUCKET_NAME` (Neon Object Storage is S3-compatible; the bucket
  stays private, the app streams bytes through authed routes); missing values
  fail fast at wiring time instead of silently using local disk. Live bucket
  verified 2026-09-18 (put/get/delete + full upload → READY cycle).
  `VITE_API_BASE_URL` → API origin.
- `ENABLE_API_DOCS=true` only if the OpenAPI schema should be public.

## Health / readiness

- `GET /api/v1/health` → `{"status": "ok", ...}` (liveness; never fails on
  missing optional credentials). Orchestrator liveness probe.
- `GET /api/v1/health/ready` → `{"ready": bool, "database": {...}}`
  (degraded, not 500, when unconfigured). Readiness gate: key off `ready`.

## Rate limiting posture

- Built in: per-email login throttle (10 failures / 5 min → 429 with
  `retry_after_seconds`); finite AI timeouts; bounded retries/top-k/counts.
- Not built in: per-IP / global edge limiting. Multi-replica deployments MUST
  front the API with gateway limiting (CDN/WAF, Render, nginx) —
  the in-process login window does not share state across replicas.

## Migrations

- Single head; additive only (`alembic heads` must print one revision).
- Deploy: `alembic upgrade head` before starting API/worker. Downgrades exist
  for rollback but enum values are intentionally never removed.
- Live-Neon upgrade executed 2026-09-18 (head `0011_qattempt_created_at`,
  single head); SQLite upgrade/downgrade paths are executed in validation.

## Development-only infrastructure (never deployed)

- The venv-local DNS fallback (`dev_dns_fallback.py` + `dev-dns-fallback.pth`
  inside `backend/.venv/`) exists only because one development machine's LAN
  DNS refuses `neon.tech`. It is gitignored (`.venv/`), is NOT part of the
  application, and MUST NOT be packaged or shipped: production hosts resolve
  Neon via normal DNS. If a deploy target shows `failed to resolve host` for
  Neon, fix that host's resolver — do not copy this workaround.

## Worker reliability notes

- Atomic job claims (+ stale-lease reclaim), bounded retries with
  transient/permanent classification, idempotent delete-then-insert rebuilds,
  FAILED states with user-safe messages. A crashed worker's RUNNING rows are
  reclaimed after `PROCESSING_STALE_CLAIM_MINUTES` (30).

## Monitoring / logging

- Structured logs with request IDs (`X-Request-ID` echoed/validated);
  per-request method/path/status/duration; AI calls log
  provider/model/operation/latency/tokens-when-reported/ids — never keys,
  prompts, answers, or document contents. Slow analytics queries log
  `dashboard_duration_ms` with project/user/range.
