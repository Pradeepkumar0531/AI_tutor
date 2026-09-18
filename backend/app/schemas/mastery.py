"""Mastery API contracts. Scores are 0-1 floats; confidence 0-1; trend from
the existing MasteryTrend vocabulary. Cold-start concepts report the baseline
with has_evidence=False — never 0% as false knowledge."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MasteryTrend


class MasteryRead(BaseModel):
    concept_id: uuid.UUID
    concept_name: str = ""
    mastery_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    trend: MasteryTrend = MasteryTrend.STABLE
    evidence_count: int = 0
    recent_performance: list[str] = Field(default_factory=list)
    has_evidence: bool = False
    updated_at: datetime | None = None


class MasteryDetailRead(MasteryRead):
    evidence_questions: int = 0
    contributing_assessments: list[uuid.UUID] = Field(default_factory=list)


class MasteryHistoryRead(BaseModel):
    id: uuid.UUID
    assessment_id: uuid.UUID | None = None
    previous_score: float | None = Field(default=None, ge=0.0, le=1.0)
    new_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
