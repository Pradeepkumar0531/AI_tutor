"""Admin API schemas. Secret-free by construction: no hashes, tokens, keys,
embeddings, storage internals, or raw payloads — only operational metadata."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AdminOverviewRead(BaseModel):
    users: int
    admins: int
    spaces: int
    projects: int
    materials: int
    materials_ready: int
    assessments: int
    quiz_attempts: int
    tutor_conversations: int
    tutor_messages: int
    active_recommendations: int
    events: int
    ai_calls: int
    evaluation_runs: int
    jobs: dict[str, int]


class AdminUserRead(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class AdminSpaceRead(BaseModel):
    id: uuid.UUID
    name: str
    project_count: int = 0


class AdminAssessmentRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    status: str
    score: float | None = None
    created_at: datetime


class AdminRecommendationRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    type: str
    title: str
    status: str


class AdminEventRead(BaseModel):
    id: uuid.UUID
    event_type: str
    user_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    created_at: datetime


class AdminUserJourneyRead(BaseModel):
    user: AdminUserRead
    project_ids: list[str]
    spaces: list[AdminSpaceRead]
    assessments: list[AdminAssessmentRead]
    recommendations: list[AdminRecommendationRead]
    mastery_concepts: int
    mastery_avg: float
    ai_requests: int
    ai_estimated_cost_usd: float
    recent_events: list[AdminEventRead]


class AdminJobRead(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    attempt_count: int
    max_retries: int
    material_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    error_summary: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AdminHealthRead(BaseModel):
    overall: str
    api: str
    database: str
    database_configured: bool
    ai: dict
    storage: dict
    queue: dict


class AdminAiUsageRead(BaseModel):
    id: str
    user_id: str | None = None
    project_id: str | None = None
    feature: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None
    success: bool
    error_type: str | None = None
    request_id: str | None = None
    created_at: str | None = None


class AdminAiSummaryItemRead(BaseModel):
    feature: str
    provider: str
    model: str
    requests: int
    failures: int
    avg_latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class AdminEvaluationFailureRead(BaseModel):
    case_id: str
    category: str
    reason: str


class AdminEvaluationCategoryRead(BaseModel):
    category: str
    total: int
    passed: int


class AdminEvaluationSummaryRead(BaseModel):
    run_id: str
    created_at: str | None = None
    total: int
    passed: int
    failed: int
    by_category: list[AdminEvaluationCategoryRead]
    recent_failures: list[AdminEvaluationFailureRead]


class AdminEvaluationRunRead(BaseModel):
    id: uuid.UUID
    triggered_by_id: uuid.UUID | None = None
    total_cases: int
    passed: int
    failed: int
    created_at: datetime
