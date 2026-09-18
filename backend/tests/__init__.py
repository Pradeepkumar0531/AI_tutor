"""Hermetic test package: never load the developer's backend/.env.

A local ``backend/.env`` may hold real Neon/AI credentials. The suite runs on
SQLite/local storage only, so dotenv loading and ambient infrastructure
secrets are neutralized here — this module is imported before conftest and any
app module constructs ``Settings``.
"""

import os

os.environ.setdefault("APP_ENV_FILE", os.devnull)
for _var in (
    "ADMIN_EMAILS",
    "DATABASE_URL",
    "CORS_ORIGINS",
    "JWT_SECRET_KEY",
    "SECRET_KEY",
    "GROQ_API_KEY",
    "GOOGLE_API_KEY",
    "UPSTASH_REDIS_URL",
    "UPSTASH_REDIS_TOKEN",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "CELERY_FILESYSTEM_ROOT",
    "STORAGE_BACKEND",
    "LOCAL_STORAGE_DIR",
    "NEON_STORAGE_ENDPOINT",
    "NEON_STORAGE_REGION",
    "NEON_STORAGE_ACCESS_KEY_ID",
    "NEON_STORAGE_SECRET_ACCESS_KEY",
    "NEON_STORAGE_BUCKET_NAME",
):
    os.environ.pop(_var, None)
