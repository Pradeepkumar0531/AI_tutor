"""Assessment API contracts. Learner-safe by construction: correct answers,
reference answers, evaluator context, prompts, embeddings, and storage keys
never appear on pre-answer payloads."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    AssessmentStatus,
    AttemptStatus,
    Difficulty,
    QuestionType,
    QuizStatus,
)

MAX_TITLE_CHARS = 200
MAX_REQUEST_KEY_CHARS = 64
MAX_ANSWER_CHARS = 10000


class QuizCreate(BaseModel):
    question_count: int = Field(default=5, ge=1, le=100)
    difficulty: Difficulty | None = None
    focus_concepts: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    question_types: list[QuestionType] | None = None
    title: str | None = Field(default=None, max_length=MAX_TITLE_CHARS)
    client_request_key: str | None = Field(default=None, max_length=MAX_REQUEST_KEY_CHARS)

    @field_validator("title")
    @classmethod
    def _non_blank_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value


class QuizRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    status: QuizStatus
    difficulty: Difficulty | None = None
    question_count: int = 0
    created_at: datetime


class LearnerOption(BaseModel):
    id: str
    text: str


class LearnerConcept(BaseModel):
    id: uuid.UUID
    name: str


class LearnerSource(BaseModel):
    material_name: str = ""
    page_start: int | None = None
    page_end: int | None = None


class LearnerQuestion(BaseModel):
    question_id: uuid.UUID
    type: QuestionType
    prompt: str
    options: list[LearnerOption] = Field(default_factory=list)
    position: int
    points: float = 1.0
    difficulty: Difficulty | None = None
    concepts: list[LearnerConcept] = Field(default_factory=list)
    sources: list[LearnerSource] = Field(default_factory=list)


class QuizDetailRead(BaseModel):
    quiz: QuizRead
    questions: list[LearnerQuestion] = Field(default_factory=list)


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    quiz_id: uuid.UUID
    status: AttemptStatus
    score: float | None = None
    max_score: float | None = None
    started_at: datetime
    completed_at: datetime | None = None


class AnswerState(BaseModel):
    submitted: str | None = None
    is_correct: bool | None = None
    score: float | None = None
    feedback: str | None = None
    correct_option_id: str | None = None
    evaluation: dict | None = None


class AttemptQuestionView(LearnerQuestion):
    answer: AnswerState = Field(default_factory=AnswerState)


class AttemptDetailRead(BaseModel):
    attempt: AttemptRead
    questions: list[AttemptQuestionView] = Field(default_factory=list)


class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)


class AnswerResult(BaseModel):
    attempt_id: uuid.UUID
    question_id: uuid.UUID
    is_correct: bool | None = None
    score: float | None = None
    points: float = 1.0
    feedback: str = ""
    is_retry_replay: bool = False
    correct_option_id: str | None = None
    evaluation: dict | None = None


class AssessmentSummaryRead(BaseModel):
    id: uuid.UUID
    quiz_attempt_id: uuid.UUID | None = None
    quiz_id: uuid.UUID | None = None
    status: AssessmentStatus
    score: float | None = None
    completed_at: datetime | None = None


class ConceptPerformanceRead(BaseModel):
    concept_id: uuid.UUID
    concept_name: str = ""
    questions_seen: int = 0
    correct_count: int = 0
    partial_count: int = 0
    incorrect_count: int = 0
    normalized_score: float = 0.0
    recent: list[str] = Field(default_factory=list)


class CompleteResult(BaseModel):
    assessment_id: uuid.UUID
    quiz_attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    total_questions: int = 0
    answered_count: int = 0
    correct_count: int = 0
    partial_count: int = 0
    incorrect_count: int = 0
    score: float = 0.0
    concept_results: list[ConceptPerformanceRead] = Field(default_factory=list)
