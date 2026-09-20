# Single-container production image: FastAPI + Celery worker side by side.
# Used by Hugging Face Spaces (Docker SDK, free CPU Basic) and any host that
# runs one container. Build context is the REPO ROOT (see .dockerignore).
# Runtime config comes ONLY from environment (HF Space secrets / host env):
#   DATABASE_URL, CELERY_BROKER_URL, CELERY_RESULT_BACKEND, JWT_SECRET_KEY,
#   CORS_ORIGINS, ADMIN_EMAILS, GROQ_API_KEY, GOOGLE_API_KEY, STORAGE_BACKEND,
#   NEON_STORAGE_* — plus PORT (HF sets 7860; default below matches).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=7860

WORKDIR /srv/backend

# Pinned deps first (better layer caching); versions frozen from the tested
# local venv (backend/requirements.txt).
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# App + migrations + single-process entrypoint.
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY scripts/start-single.sh /srv/start-single.sh
RUN chmod +x /srv/start-single.sh

ENV PYTHONPATH=/srv/backend \
    APP_ENV=production \
    DEBUG=false

EXPOSE 7860

CMD ["/srv/start-single.sh"]
