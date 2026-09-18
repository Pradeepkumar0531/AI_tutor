# AI Learning Companion

AI-powered learning platform organized around the learning loop:

**Space → Project → Material → Knowledge → Tutor → Quiz → Assessment → Mastery → Growth → Recommendation → Continue Learning**

> Knowledge/RAG phase (Prompt 6): READY documents embed via Google
> text-embedding-004 into pgvector (validated 768-d), concepts extracted via
> Groq structured JSON with provenance, and project-scoped RAG search returns
> grounded context with app-built citations plus explicit insufficient
> evidence. Tutor phase (Prompt 7): project-scoped tutor conversations reuse
> the RAG pipeline — deterministic intent routing, app-owned grounded/
> insufficient flags, persisted citations, idempotent sends. Assessment phase
> (Prompt 8): adaptive quiz engine — grounded generation, deterministic MCQ
> grading, structured open-ended evaluation, immutable per-concept results.
> Mastery phase (Prompt 9): deterministic per-concept mastery + confidence
> from assessment evidence, with immutable history, trends, and explanations
> feeding Tutor context and adaptive selection. Growth phase (Prompt 10):
> project growth status/counts/history interpreted from mastery plus
> deterministic, lifecycle-managed recommendations wired to real Tutor, quiz,
> and material actions. Analytics phase (Prompt 11): read-only dashboard over
> persisted state + the event activity stream — summary cards, activity and
> mastery charts, timeline — with honest cold-start states and zero fake
> metrics. Document-image enhancement:
> embedded PDF rasters are extracted with exact page provenance, stored via
> StorageService, and served through authorized metadata/bytes endpoints —
> without any vision model (contents not yet understood).

## Architecture summary

Modular monolith:

```
React + TypeScript (Vite + Tailwind)  →  FastAPI REST API  →  PostgreSQL + pgvector (Neon)
                                                             →  Redis queue (Upstash) → Celery worker
                                                             →  Neon Object Storage (S3)
                                                             →  Groq LLM + Google embeddings
```

- Business logic lives in `backend/app/services/` (never in routes or React components).
- AI access only via `backend/app/ai/service.py`. Storage only via `backend/app/storage/`.
- Background work only via `backend/app/jobs/`. See `docs/ARCHITECTURE.md`.

## Tech stack

Frontend: React 18, TypeScript (strict), Vite 5, Tailwind CSS 3, shadcn-style UI primitives,
Zustand, Axios, Recharts, Outfit font, Vitest, Playwright.
Backend: FastAPI, Pydantic Settings, SQLAlchemy 2.x, Alembic, PostgreSQL + pgvector (Neon),
Upstash Redis, Celery (+ Flower, optional), JWT, Argon2id, Pytest, HTTPX.

## Repository structure

```
frontend/   # React app (src/app, components, features, api, stores, ...)
backend/    # FastAPI app (app/core, api, db, models, services, ai, rag, jobs, storage, ...)
docs/       # Architecture, development, environment, ... guides
scripts/    # Dev automation
.github/    # CI
```

## Prerequisites

- Node 18+ and npm
- Python 3.11+
- Neon PostgreSQL connection string (or leave `DATABASE_URL` empty for degraded local dev)
- Upstash Redis URL (optional for local API dev; required for real background jobs)

## Setup

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # fill values, see docs/ENVIRONMENT.md

# Frontend
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Run (3 terminals, no Docker)

```bash
# Terminal 1 — frontend
cd frontend && npm run dev            # http://localhost:5173

# Terminal 2 — API
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000   # http://127.0.0.1:8000/docs

# Terminal 3 — worker
cd backend && source .venv/bin/activate
celery -A app.jobs.worker.celery worker --loglevel=info

# Optional — Flower
celery -A app.jobs.worker.celery flower --port=5555
```

## Migrations

```bash
cd backend
alembic upgrade head          # requires DATABASE_URL
alembic revision --autogenerate -m "describe change"
```

## Tests / quality

```bash
# Backend
cd backend && pytest && ruff check . && ruff format --check . && mypy app

# Frontend
cd frontend
npm run typecheck && npm run lint && npm test && npm run build
npx playwright test   # E2E (dev server)
```

## API docs

- Development: `http://127.0.0.1:8000/docs`, `http://127.0.0.1:8000/openapi.json`
- Versioned base: `/api/v1` — `GET /api/v1/health`, `GET /api/v1/health/ready`
- Auth: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`,
  `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`
- Scoped resources (Bearer required, 404 across tenants): `/api/v1/spaces`
  (CRUD + archive/restore + search), `/api/v1/projects` (CRUD + archive/restore,
  space filter + search), `/api/v1/projects/{id}/materials`
- Full reference: `docs/API.md`

## Docs

- `docs/ARCHITECTURE.md` — system + domain diagrams, boundaries
- `docs/DEVELOPMENT.md` — copy-paste dev workflow
- `docs/ENVIRONMENT.md` — every env var explained
- `docs/DATABASE.md`, `docs/AI_ARCHITECTURE.md`, `docs/RAG.md`, `docs/DOCUMENT_PROCESSING.md`
- `docs/ASSESSMENT_ENGINE.md`, `docs/MASTERY.md` (planned), `docs/SECURITY.md`, `docs/TESTING.md`
- `docs/API.md` — endpoint reference + status semantics + rate-limit boundary
- `docs/DEPLOYMENT.md`, `docs/TROUBLESHOOTING.md`, `docs/LIMITATIONS.md`

## Security notes

- Never commit `.env`. Only `.env.example` is tracked.
- `SECRET_KEY`, `JWT_SECRET_KEY`, `DATABASE_URL`, `GROQ_API_KEY`, `GOOGLE_API_KEY`,
  Upstash + Neon-storage credentials are server-only. Never use `VITE_*` for secrets.

## Current status

Implemented: app shell + design tokens + API client + versioned API + health probes +
error envelope + request IDs + structured logging + CORS + config + DB session/Alembic +
AI/storage/job/RAG/document boundaries + auth/authz (register/login/logout/me, JWT Bearer,
ownership-scoped spaces/projects/materials, 404 IDOR protection, audit events) +
Spaces/Projects UI (lists, detail pages, workspace, dialogs, archive/restore) +
materials pipeline (PDF upload, local/Neon-object storage, Celery worker, PyMuPDF +
PaddleOCR fallback, deterministic chunking, READY/FAILED UI with polling and
document inspection) + knowledge/RAG (embeddings, concepts with provenance,
project-scoped search with app-built citations + insufficient evidence) +
grounded AI tutor (project conversations, intent routing, persisted citations,
idempotent sends, Tutor UI with grounded/insufficient badges) + adaptive quiz
engine (concept selection strategy, grounded generation, MCQ/open-ended
evaluation, server-side completion, per-concept results, Quiz UI) + mastery
engine (deterministic per-concept mastery/confidence/trends, immutable
history, explanations, Tutor + quiz integration, Mastery UI) + growth &
recommendations (project growth status/counts/history, deterministic
recommendation rules with lifecycle/dedup, Growth + Recommendations UI) +
analytics & dashboard (read-only aggregates, event feed, charts) +
production hardening (JWT/CORS/docs/throttle/timeouts/pool guards, security
matrix, smoke suite) + admin RBAC + dashboard (users/journeys/activity/jobs/
AI usage/evaluation/health) + global analytics + home/continue-learning +
persistent learning context + repeated-mistake workflow + persisted AI usage +
curated AI evaluation (16 cases) + tests + CI.
All learning-loop phases complete, hardened, and PRD-traceable
(`docs/PRD_TRACEABILITY.md`); remaining work is deployment verification
against live providers.
