"""Centralized domain enums. Single source of truth — no magic strings in code.

All enums are ``str``-based so values read naturally in APIs/logs. They persist as
native PostgreSQL ENUM types (see the Alembic migration); on SQLite they degrade to
VARCHAR, which is sufficient for the test suite.
"""

from __future__ import annotations

import enum


class MaterialType(enum.StrEnum):
    PDF = "PDF"
    URL = "URL"
    TEXT = "TEXT"
    NOTE = "NOTE"


class MaterialStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class ExtractionMethod(enum.StrEnum):
    TEXT = "TEXT"
    OCR = "OCR"
    MIXED = "MIXED"


class MessageRole(enum.StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    SYSTEM = "SYSTEM"
    TOOL = "TOOL"


class Difficulty(enum.StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class QuizStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    ARCHIVED = "ARCHIVED"


class QuestionType(enum.StrEnum):
    MCQ = "MCQ"
    OPEN_ENDED = "OPEN_ENDED"


class AttemptStatus(enum.StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


class AssessmentStatus(enum.StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MasteryTrend(enum.StrEnum):
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"


class MasterySource(enum.StrEnum):
    ASSESSMENT = "ASSESSMENT"
    QUIZ = "QUIZ"
    TUTOR = "TUTOR"
    SYSTEM = "SYSTEM"


class GrowthStatus(enum.StrEnum):
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    REQUIRING_ATTENTION = "REQUIRING_ATTENTION"


class RecommendationType(enum.StrEnum):
    REVIEW_CONCEPT = "REVIEW_CONCEPT"
    PRACTICE_QUIZ = "PRACTICE_QUIZ"
    STUDY_MATERIAL = "STUDY_MATERIAL"
    TUTOR_SESSION = "TUTOR_SESSION"


class RecommendationStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    DISMISSED = "DISMISSED"
    EXPIRED = "EXPIRED"


class ConceptRelationType(enum.StrEnum):
    PREREQUISITE = "PREREQUISITE"
    RELATED = "RELATED"
    PART_OF = "PART_OF"
    DEPENDS_ON = "DEPENDS_ON"


class JobStatus(enum.StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class EventType(enum.StrEnum):
    SPACE_CREATED = "SPACE_CREATED"
    PROJECT_CREATED = "PROJECT_CREATED"
    MATERIAL_UPLOADED = "MATERIAL_UPLOADED"
    MATERIAL_PROCESSING_STARTED = "MATERIAL_PROCESSING_STARTED"
    MATERIAL_READY = "MATERIAL_READY"
    MATERIAL_FAILED = "MATERIAL_FAILED"
    EMBEDDING_STARTED = "EMBEDDING_STARTED"
    EMBEDDING_COMPLETED = "EMBEDDING_COMPLETED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"
    CONCEPTS_EXTRACTED = "CONCEPTS_EXTRACTED"
    TUTOR_MESSAGE = "TUTOR_MESSAGE"
    TUTOR_RESPONSE = "TUTOR_RESPONSE"
    CONVERSATION_CREATED = "CONVERSATION_CREATED"
    QUIZ_CREATED = "QUIZ_CREATED"
    QUIZ_STARTED = "QUIZ_STARTED"
    QUESTION_ANSWERED = "QUESTION_ANSWERED"
    ASSESSMENT_COMPLETED = "ASSESSMENT_COMPLETED"
    MASTERY_UPDATED = "MASTERY_UPDATED"
    RECOMMENDATION_GENERATED = "RECOMMENDATION_GENERATED"
    USER_REGISTERED = "USER_REGISTERED"
    USER_LOGIN_SUCCEEDED = "USER_LOGIN_SUCCEEDED"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED"
    USER_LOGOUT = "USER_LOGOUT"
