"""Growth + recommendation API contracts. All numbers are server-computed
from persisted learning state; the frontend never calculates them."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import (
    GrowthStatus,
    MasteryTrend,
    RecommendationStatus,
    RecommendationType,
)


class ConceptGrowthRead(BaseModel):
    concept_id: uuid.UUID
    concept_name: str = ""
    status: GrowthStatus
    mastery_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    trend: MasteryTrend = MasteryTrend.STABLE
    change_score: float | None = None
    summary: str = ""


class GrowthRead(BaseModel):
    project_id: uuid.UUID
    status: GrowthStatus
    has_evidence: bool
    overall_mastery: float = Field(ge=0.0, le=1.0)
    average_confidence: float = Field(ge=0.0, le=1.0)
    concepts_improving: int = 0
    concepts_stable: int = 0
    concepts_requiring_attention: int = 0
    assessed_concepts: int = 0
    assessment_count: int = 0
    questions_answered: int = 0
    updated_at: datetime | None = None
    concepts: list[ConceptGrowthRead] = Field(default_factory=list)


class GrowthHistoryPointRead(BaseModel):
    date: datetime
    score: float = Field(ge=0.0, le=1.0)
    assessment_id: uuid.UUID


class RecommendationRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    concept_id: uuid.UUID | None = None
    concept_name: str = ""
    material_id: uuid.UUID | None = None
    material_name: str = ""
    type: RecommendationType
    title: str
    description: str | None = None
    reason: str | None = None
    actions: list[str] = Field(default_factory=list)
    priority: int = 0
    status: RecommendationStatus
    source_assessment_id: uuid.UUID | None = None
    created_at: datetime
    completed_at: datetime | None = None
