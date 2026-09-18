# Environment

NEVER expose backend secrets through `VITE_*` variables. Only `VITE_API_BASE_URL` is
frontend-safe.

## Frontend (`frontend/.env`)

| Variable | Required | Purpose | Example |
|---|---|---|---|
| `VITE_API_BASE_URL` | yes (dev default works) | Backend origin for the Axios client | `http://127.0.0.1:8000` |

## Backend (`backend/.env`)

| Variable | Required | Source | Example |
|---|---|---|---|
| `APP_NAME` | no | any | `AI Learning Companion` |
| `APP_ENV` | no | local/development/staging/production | `local` |
| `DEBUG` | no | `true` locally | `true` |
| `API_PREFIX` | no | keep `/api/v1` | `/api/v1` |
| `SECRET_KEY` | yes (prod) | generate random | `change-me-...` |
| `CORS_ORIGINS` | yes | comma-separated frontend origins | `http://localhost:5173` |
| `DATABASE_URL` | prod yes / local optional | Neon dashboard | `postgresql+psycopg://user:pw@host/db` |
| `GROQ_API_KEY` | when using tutor/quiz AI + concept extraction | Groq console | `gsk_...` |
| `GOOGLE_API_KEY` | when using embeddings | Google AI Studio | `AIza...` |
| `GOOGLE_EMBEDDING_MODEL` | no | must emit 768-d vectors | `models/text-embedding-004` |
| `EMBEDDING_DIMENSIONS` | no | must be 768 (startup refuses anything else) | `768` |
| `GROQ_MODEL_CONCEPTS` | no | chat model for concept extraction | `llama-3.1-8b-instant` |
| `EMBEDDING_BATCH_SIZE` | no | texts per provider call | `32` |
| `EMBEDDING_TIMEOUT_SECONDS` | no | per-batch timeout | `60` |
| `EMBEDDING_MAX_RETRIES` | no | transient retries per batch | `3` |
| `RAG_TOP_K` | no | default results per search (clamped 1–50) | `8` |
| `RAG_SIMILARITY_THRESHOLD` | no | default minimum cosine similarity (0–1) | `0.3` |
| `RAG_MAX_CONTEXT_CHUNKS` | no | context budget in chunks (≤50) | `8` |
| `RAG_MAX_CONTEXT_CHARS` | no | context budget in chars (≤200k) | `12000` |
| `CONCEPT_MAX_INPUT_CHARS` | no | extraction input budget | `12000` |
| `CONCEPT_MAX_PER_RUN` | no | concepts persisted per run | `20` |
| `TEST_FAKE_AI` | test/E2E only, never prod | deterministic fake AI providers | `false` |
| `UPSTASH_REDIS_URL` | for real queues | Upstash dashboard | `rediss://...` |
| `UPSTASH_REDIS_TOKEN` | for Upstash REST (if used) | Upstash dashboard | `...` |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | optional overrides | Redis URL | `redis://localhost:6379/0` |
| `NEON_STORAGE_ENDPOINT` | when `STORAGE_BACKEND=neon` | S3-compatible endpoint from the Neon console | — |
| `NEON_STORAGE_REGION` | no (neon) | bucket region for request signing | — |
| `NEON_STORAGE_ACCESS_KEY_ID` / `NEON_STORAGE_SECRET_ACCESS_KEY` / `NEON_STORAGE_BUCKET_NAME` | when `STORAGE_BACKEND=neon` | Neon Object Storage credentials/bucket | — |
| `GOOGLE_EMBEDDING_MODEL` | no | embedding model id | `models/gemini-embedding-001` |
| `GOOGLE_EMBEDDING_DIMENSIONS` | no | requested width; must equal 768 (schema) | `768` |
| `STORAGE_BACKEND` | no | `local` (dev/test) or `neon` (production) | `local` |
| `LOCAL_STORAGE_DIR` | no | local object dir | `./storage` |
| `JWT_SECRET_KEY` | yes (prod) | generate random, ≥32 chars | `change-me-...` |
| `ADMIN_EMAILS` | no | comma-separated bootstrap admin emails (promoted on register/login) | — |
| `JWT_ALGORITHM` | no | `HS256` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | access-token lifetime | `30` |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_ATTEMPT_WINDOW_SECONDS` | no | failed logins per email per window before 429 | `10` / `300` |
| `GROQ_TIMEOUT_SECONDS` | no | finite client timeout for every Groq call | `60` |
| `ENABLE_API_DOCS` | no | serve `/docs` + `/openapi.json` in production (always on in dev) | `false` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT_SECONDS` / `DB_POOL_RECYCLE_SECONDS` | no | SQLAlchemy pool tuning (same pool for SQLite) | `5` / `10` / `30` / `1800` |

## Materials / processing (`backend/.env`)

| Variable | Required | Purpose | Example |
|---|---|---|---|
| `MAX_UPLOAD_BYTES` | no | PDF upload cap (validated pre-storage) | `26214400` (25 MB) |
| `PROCESSING_MAX_PAGES` | no | hard page cap, else permanent FAILED | `500` |
| `PROCESSING_MAX_CHARS` | no | hard extracted-text cap | `2000000` |
| `PROCESSING_CHUNK_SIZE` | no | target chunk chars | `1000` |
| `PROCESSING_CHUNK_OVERLAP` | no | trailing-char overlap within a page | `150` |
| `PROCESSING_MIN_CHUNK_CHARS` | no | short-tail merge threshold | `100` |
| `OCR_MIN_CHARS_PER_PAGE` | no | pages below this are OCR candidates | `50` |
| `OCR_ENABLED` | no | `false` disables OCR (empty pages fail fast) | `true` |
| `PDF_IMAGE_EXTRACTION_ENABLED` | no | `false` skips embedded-image extraction | `true` |
| `PDF_MIN_IMAGE_WIDTH` / `PDF_MIN_IMAGE_HEIGHT` | no | smaller images are decor, filtered | `100` / `100` |
| `PDF_MIN_IMAGE_BYTES` | no | smaller binaries are icons/pixels, filtered | `2048` |
| `PDF_MAX_IMAGES_PER_PAGE` / `PDF_MAX_IMAGES_PER_DOCUMENT` | no | deterministic caps (first N kept) | `10` / `50` |
| `PROCESSING_STALE_CLAIM_MINUTES` | no | reclaim RUNNING claims older than this (crash recovery) | `30` |
| `CELERY_FILESYSTEM_ROOT` | dev/E2E only | filesystem-broker root when `CELERY_BROKER_URL=filesystem://` | `/tmp/alc-celery-fs` |

Auth behavior notes:

- With `APP_ENV=production`, issuing a token with the dev-default or a short
  `JWT_SECRET_KEY` raises `RuntimeError` at startup-of-use instead of minting
  weak tokens. Generate with e.g. `python -c "import secrets; print(secrets.token_hex(32))"`.
- `CORS_ORIGINS` must list the exact frontend origin(s); Bearer auth needs no
  cookies, but `allow_credentials` is on, so `*` is never used.
- No refresh-token or session-table variables exist in this phase by design
  (stateless short-lived JWTs; see `docs/SECURITY.md`).

Without `DATABASE_URL`, the API still boots; `/health/ready` reports `database.configured=false`.
Without Groq/Google keys, AI calls raise a clear `RuntimeError` instead of failing at import.
