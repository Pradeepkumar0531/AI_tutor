"""Event + processing-job schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import EventType, JobStatus


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    event_type: EventType
    entity_type: str | None
    entity_id: uuid.UUID | None
    payload: dict[str, Any] | None
    created_at: datetime


class ProcessingJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    material_id: uuid.UUID | None
    job_type: str
    status: JobStatus
    attempt_count: int
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
