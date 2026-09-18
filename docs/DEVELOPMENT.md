# Development

Expectations: Node 18+, Python 3.11+.

```bash
# Backend setup
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# Frontend setup
cd frontend
npm install
cp .env.example .env
```

Run (no Docker):

```bash
# Terminal 1
cd frontend && npm run dev
# Terminal 2
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
# Terminal 3
cd backend && source .venv/bin/activate && celery -A app.jobs.worker.celery worker --loglevel=info
# Optional Flower
celery -A app.jobs.worker.celery flower --port=5555
```

Terminal 3 needs a brchange-me-generate-a-long-jwt-secretoker: production uses `UPSTASH_REDIS_URL`; local dev
without Redis can use the filesystem stand-in
(`CELERY_BROKER_URL=filesystem://`, optional `CELERY_FILESYSTEM_ROOT`).
Same worker code either way.

Migrations / tests / quality:

```bash
cd backend
alembic upgrade head
pytest
ruff check . && ruff format --check .
mypy app

cd ../frontend
npm run typecheck && npm run lint && npm test && npm run build
npx playwright test
```

## Local auth flow

1. Start the API with a database (`DATABASE_URL`; SQLite file works for a
   smoke run, Neon for real dev) and run `alembic upgrade head`.
2. Open the frontend, register at `/register` — you land in the app with a
   Bearer session persisted in `localStorage` (`alc.access_token`).
3. Reload: the app calls `GET /api/v1/auth/me` and restores the session with
   no content flash. Sign out via the top-right menu clears the token.
4. Local admin: set `ADMIN_EMAILS=you@example.com`, register that email, and
   open `/admin` (server-side `require_admin`; the UI only hides the link).
   E2E covers the admin journey in `tests/e2e/admin.spec.ts`
   (`ADMIN_EMAILS=e2e-admin@example.com` in `global-setup.ts`).
6. E2E (`npx playwright test`) boots frontend + API + a real Celery worker
   subprocess itself (isolated SQLite, filesystem broker, fresh schema and a
   generated 2-page PDF fixture per run, `TEST_FAKE_AI=true` for deterministic
   content-derived fake providers) and walks register → upload → READY →
   knowledge READY → grounded search with citations → tutor grounded journey
   with fallbacks/history/idempotency → quiz generation/attempt/completion
   with adaptive resurfacing → mastery list/detail/history with completion-
   driven updates → growth overview with distribution → recommendations with
   lifecycle actions → dashboard cards/charts/timeline → logout, plus
   cross-tenant denial. Quiz E2E
   relies on two fake-AI contracts: generated MCQ correct answers are always
   the first option, and open-ended scoring is word-overlap with the
   reference (see `FakeChatProvider` quiz modes). Mastery calculations in E2E
   always run the real production algorithm.
5. To exercise knowledge locally without Google/Groq keys, run the API and
   worker with `TEST_FAKE_AI=true` (dev only — never in production); with real
   keys set, the same code paths call the live providers instead.

## Production security considerations

- Set `APP_ENV=production`, `DEBUG=false`, a real `JWT_SECRET_KEY` (≥32 random
  chars), and the exact Vercel origin in `CORS_ORIGINS`.
- Serve the API over HTTPS; Bearer tokens are only as safe as the transport.
- Rotate `JWT_SECRET_KEY` to invalidate all sessions at once (stateless JWTs
  have no per-token revocation in this phase).
