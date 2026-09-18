"""Analytics + event feed contracts. Every number is a server-computed
aggregate over persisted state; cold start uses nulls, never zeros-as-failure."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import EventType, GrowthStatus


class AttentionItemRead(BaseModel):
    project_id: uuid.UUID
    concept: str
    change: float


class GlobalSummaryRead(BaseModel):
    projects: int
    materials: int
    materials_ready: int
    assessments: int
    questions_answered: int
    tutor_messages: int
    mastery_avg: float
    mastery_concepts: int
    attention: list[AttentionItemRead]
    active_recommendations: int
    recent_project_ids: list[uuid.UUID]
    last_activity_at: datetime | None = None


class HomeNextActionRead(BaseModel):
    kind: str
    title: str
    reason: str
    project_id: uuid.UUID
    recommendation_id: uuid.UUID | None = None


class HomeContinueRead(BaseModel):
    project_id: uuid.UUID
    project_name: str
    space_id: uuid.UUID
    materials: int
    next_action: HomeNextActionRead


class HomeProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    space_id: uuid.UUID
    updated_at: datetime | None = None


class HomeProgressRead(BaseModel):
    projects: int
    materials: int
    materials_ready: int
    assessments: int
    questions_answered: int
    mastery_avg: float
    mastery_concepts: int


class HomeRead(BaseModel):
    continue_learning: HomeContinueRead | None = None
    recent_projects: list[HomeProjectRead]
    progress: HomeProgressRead
    attention: list[AttentionItemRead]
    recommended_action: HomeNextActionRead | None = None


class DashboardSummaryRead(BaseModel):
    project_id: uuid.UUID
    project_name: str = ""
    materials_count: int = 0
    materials_ready: int = 0
    materials_failed: int = 0
    documents_count: int = 0
    pages_count: int = 0
    chunks_count: int = 0
    images_count: int = 0
    concepts_count: int = 0
    assessment_count: int = 0
    questions_answered: int = 0
    questions_correct: int = 0
    questions_partial: int = 0
    questions_incorrect: int = 0
    average_assessment_score: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_mastery: float | None = Field(default=None, ge=0.0, le=1.0)
    mastery_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    growth_status: GrowthStatus | None = None
    active_recommendations: int = 0
    tutor_conversations: int = 0
    tutor_messages: int = 0
    last_activity_at: datetime | None = None
    has_learning_evidence: bool = False


class ActivityItemRead(BaseModel):
    id: uuid.UUID
    event_type: EventType
    created_at: datetime
    resource_id: uuid.UUID | None = None
    metadata: dict | None = None
    summary: str = ""


class ActivityDayRead(BaseModel):
    date: str
    count: int = 0


class MasteryTrendPointRead(BaseModel):
    date: datetime
    score: float = Field(ge=0.0, le=1.0)
    assessment_id: uuid.UUID


class EventRead(BaseModel):
    id: uuid.UUID
    event_type: EventType
    created_at: datetime
    project_id: uuid.UUID | None = None
    resource_id: uuid.UUID | None = None
    metadata: dict | None = None
