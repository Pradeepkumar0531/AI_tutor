"""Worker entrypoint: `celery -A app.jobs.worker.celery worker --loglevel=info`."""

from app.jobs.celery_app import celery_app

# Alias matching the documented `-A app.jobs.worker.celery` reference.
celery = celery_app

__all__ = ["celery", "celery_app"]
