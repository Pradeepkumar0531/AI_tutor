# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `DATABASE_URL is not configured` on session use | Set `DATABASE_URL` in `backend/.env`; `/health/ready` shows `configured:false` otherwise |
| CORS errors in browser | Add frontend origin to `CORS_ORIGINS`, restart API |
| Frontend shows "Backend unreachable" | API not running or `VITE_API_BASE_URL` wrong; check `/api/v1/health` with curl |
| Celery broker connection refused | Set `UPSTASH_REDIS_URL` or run local redis; API itself boots without it |
| Uploaded material stuck in QUEUED | No worker consuming: check the worker process, broker URL, and that API + worker share `CELERY_BROKER_URL`/`CELERY_FILESYSTEM_ROOT`. Local dev without Redis: `CELERY_BROKER_URL=filesystem://` |
| Material FAILED "needs OCR but is not installed" | No OCR engine found: install the `tesseract` binary (light) or `pip install -e ".[ocr]"` for PaddleOCR (heavy), then reprocess; or upload a text PDF |
| Material FAILED "no readable text" | Scanned/blank PDF with nothing extractable; re-upload a text PDF or enable OCR |
| Reprocess returns 409 | Only `FAILED` materials with no pending job can reprocess; `READY` is immutable |
| Login returns 429 `RATE_LIMITED` | Per-email throttle (default 10 failures / 5 min); wait out `retry_after_seconds`, check caps |
| `CORS_ORIGINS must be set explicitly in production` at startup | Production requires explicit origins; dev defaults are refused — set `CORS_ORIGINS` |
| `/docs` or `/openapi.json` 404 in production | Intended: set `ENABLE_API_DOCS=true` to expose them |
| `JWT_SECRET_KEY is not configured for production` at startup | Set a random ≥32-char secret; dev default is refused under `APP_ENV=production` |
| `GROQ_API_KEY`/`GOOGLE_API_KEY` errors | Expected until keys set; AI calls raise clear `RuntimeError` |
| Alembic "no database" | `alembic` commands needing DB require `DATABASE_URL`; `history`/`check` work without |
