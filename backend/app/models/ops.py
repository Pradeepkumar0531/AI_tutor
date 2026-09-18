"""Platform operations: append-only Events + ProcessingJob state.

Events answer "what happened"; ProcessingJobs answer "what is processing, what
failed, how many retries, why". Historical rows are never updated or deleted by
application code (user/project deletion uses SET NULL to preserve the audit trail).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import EventType, JobStatus
from app.models.mixins import CreatedMixin, FlexibleJSON, TimestampMixin

if TYPE_CHECKING:
    from app.models.learning import Project
    from app.models.materials import Material
    from app.models.users import User


class Event(Base, CreatedMixin):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[EventType] = mapped_column(
        sa.Enum(EventType, name="event_type"), nullable=False, index=True
    )
    entity_type: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(FlexibleJSON, nullable=True)

    __table_args__ = (sa.Index("ix_events_project_created", "project_id", "created_at"),)

    user: Mapped[User | None] = relationship()
    project: Mapped[Project | None] = relationship(back_populates="events")


class ProcessingJob(Base, TimestampMixin):
    """Persistence for background work (pairs with Celery tasks in app/jobs/).

    One row per unit of work. ``idempotency_key`` lets producers safely re-enqueue;
    ``attempt_count``/``max_retries``/``error`` expose pipeline health.
    """

    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("materials.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    job_type: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(JobStatus, name="job_status"),
        nullable=False,
        default=JobStatus.QUEUED,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=3)
    idempotency_key: Mapped[str | None] = mapped_column(sa.String(128), nullable=True, unique=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(FlexibleJSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempts"),
        sa.CheckConstraint("max_retries >= 0", name="ck_jobs_max_retries"),
    )

    material: Mapped[Material | None] = relationship()
    project: Mapped[Project | None] = relationship(back_populates="processing_jobs")
