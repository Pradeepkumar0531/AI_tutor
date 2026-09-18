"""Celery task dispatch: API-side fire-and-forget with honest failure modes.

Called by routes *after* the service transaction commits, so the worker never
races uncommitted rows. If the broker is unreachable, the ProcessingJob row
stays QUEUED (a worker or reprocess picks it up later) and the upload still
returns 201 — dispatch failure is logged, never fatal to the request.
"""

from __future__ import annotations

import logging
import uuid

log = logging.getLogger("app.jobs.dispatch")


def _publish(task, material_id: uuid.UUID, task_name: str) -> bool:
    from kombu.exceptions import OperationalError

    try:
        task.delay(str(material_id))
    except (OperationalError, ConnectionError, OSError, RuntimeError) as e:
        # RuntimeError covers celery's publish-time retry-limit errors (broker
        # or result store unreachable). The job row stays QUEUED either way.
        log.warning(
            "broker unreachable, job stays QUEUED task=%s material_id=%s err=%s",
            task_name,
            material_id,
            e,
        )
        return False
    return True


def dispatch_processing(material_id: uuid.UUID) -> bool:
    """Enqueue ``process_material`` for a committed material. Returns True when
    the message reached the broker."""
    from app.jobs.document_tasks import process_material

    return _publish(process_material, material_id, "process_material")


def dispatch_knowledge(material_id: uuid.UUID) -> bool:
    """Enqueue ``process_knowledge`` for a READY material. Same best-effort
    contract: failure leaves the job QUEUED for a later worker or reprocess."""
    from app.jobs.knowledge_tasks import process_knowledge

    return _publish(process_knowledge, material_id, "process_knowledge")
