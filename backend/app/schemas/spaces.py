"""Space + Project schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import Difficulty


class SpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class SpaceUpdate(BaseModel):
    """Only explicit metadata fields are writable — never owner/ids/timestamps."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class SpaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    icon: str | None
    color: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    project_count: int | None = None


class ProjectCreate(BaseModel):
    space_id: uuid.UUID
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    learning_goal: str | None = None


class ProjectUpdate(BaseModel):
    """Only explicit metadata fields are writable — never owner/space/ids/metrics."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    learning_goal: str | None = None
    target_outcome: str | None = None
    difficulty: Difficulty | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    space_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    learning_goal: str | None
    target_outcome: str | None = None
    difficulty: Difficulty | None = None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    material_count: int | None = None
