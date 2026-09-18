"""Atomic ProcessingJob claiming. Exactly one worker may own a job at a time.

The claim is a single conditional UPDATE (QUEUED/RETRYING, or a stale RUNNING
lease treated as crashed) — correct across processes on PostgreSQL and SQLite
with no memory locks and no Redis flags.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.mixins import utcnow
from app.models.ops import JobStatus, ProcessingJob


def idempotency_key(material_id: uuid.UUID, *, suffix: str) -> str:
    """Stable per-material job keys, e.g. ``material:<id>:process``."""
    return f"material:{material_id}:{suffix}"


def get_or_create_job(
    session: Session,
    *,
    job_type: str,
    project_id: uuid.UUID | None,
    material_id: uuid.UUID,
    idempotency_key: str,
    payload: dict | None = None,
) -> ProcessingJob:
    job = session.scalar(
        sa.select(ProcessingJob).where(ProcessingJob.idempotency_key == idempotency_key)
    )
    if job is None:  # defensive: tasks are independently executable
        job = ProcessingJob(
            job_type=job_type,
            project_id=project_id,
            material_id=material_id,
            idempotency_key=idempotency_key,
            payload=payload or {"material_id": str(material_id)},
        )
        session.add(job)
        session.flush()
    return job


def claim_job(session: Session, job: ProcessingJob, settings: Settings) -> bool:
    """Attempt the atomic claim. Returns True iff this worker now owns the job;
    also bumps attempt_count and clears any previous terminal markers."""
    stale_before = utcnow() - timedelta(minutes=settings.processing_stale_claim_minutes)
    claimed = (
        session.connection()
        .execute(
            sa.update(ProcessingJob)
            .where(
                ProcessingJob.id == job.id,
                sa.or_(
                    ProcessingJob.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]),
                    sa.and_(
                        ProcessingJob.status == JobStatus.RUNNING,
                        ProcessingJob.started_at.is_not(None),
                        ProcessingJob.started_at < stale_before,
                    ),
                ),
            )
            .values(
                status=JobStatus.RUNNING,
                attempt_count=ProcessingJob.attempt_count + 1,
                started_at=utcnow(),
                completed_at=None,
                error=None,
            )
        )
        .rowcount
    )
    session.flush()
    return bool(claimed)
