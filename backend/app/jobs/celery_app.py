"""Celery foundation: broker = Redis/Upstash, API only enqueues, worker executes.

Broker selection is configuration, not code: production uses Upstash Redis while
local dev/E2E may point ``CELERY_BROKER_URL`` at ``filesystem://`` (real broker
semantics — message files on disk — with zero infrastructure). The task code is
identical either way.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from celery import Celery, Task

from app.core.config import get_settings

log = logging.getLogger("app.jobs")


class LoggedTask(Task):
    autoretry_for = (Exception,)
    max_retries = 3
    default_retry_delay = 30

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # type: ignore[no-untyped-def]
        log.error("task failed id=%s name=%s err=%s", task_id, self.name, exc)
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):  # type: ignore[no-untyped-def]
        log.info("task ok id=%s name=%s", task_id, self.name)
        super().on_success(retval, task_id, args, kwargs)


def _filesystem_transport_options(broker_url: str) -> dict:
    """kombu filesystem transport needs explicit data folders. Note the
    inverted semantics: producers write to ``data_folder_out`` while consumers
    read from ``data_folder_in`` — so a broker shared by the API (producer)
    and the worker (consumer) must point both at the SAME directory."""
    from app.core.config import get_settings as _settings

    root = _settings().celery_filesystem_root or os.path.join(os.getcwd(), ".celery-fs")
    queue = os.path.join(root, "queue")
    folders = {
        "data_folder_in": queue,
        "data_folder_out": queue,
        "data_folder_processed": os.path.join(root, "processed"),
    }
    for folder in folders.values():
        os.makedirs(folder, exist_ok=True)
    return folders


def make_celery() -> Celery:
    settings = get_settings()
    broker_url = settings.broker_url
    is_filesystem = urlparse(broker_url).scheme == "filesystem"
    transport_options = _filesystem_transport_options(broker_url) if is_filesystem else {}
    result_backend = settings.result_backend
    if is_filesystem and not (settings.celery_result_backend or settings.upstash_redis_url):
        # No Redis configured alongside the filesystem broker (dev/E2E): keep
        # results on disk too instead of pointing at an unreachable Redis.
        root = settings.celery_filesystem_root or os.path.join(os.getcwd(), ".celery-fs")
        os.makedirs(os.path.join(root, "results"), exist_ok=True)
        result_backend = f"file://{os.path.join(root, 'results')}"
    celery = Celery(
        "ai_learning_companion",
        broker=broker_url,
        backend=result_backend,
        task_cls=LoggedTask,
        broker_transport_options=transport_options,
    )
    celery.conf.update(
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_time_limit=30 * 60,
        task_soft_time_limit=25 * 60,
    )
    celery.autodiscover_tasks(["app.jobs"], related_name="document_tasks")
    celery.autodiscover_tasks(["app.jobs"], related_name="knowledge_tasks")
    return celery


celery_app = make_celery()


@celery_app.task(name="app.jobs.ping")
def ping() -> str:
    return "pong"
