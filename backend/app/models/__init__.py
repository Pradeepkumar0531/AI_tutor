"""Domain model registry. Import every model module so relationships resolve and
Alembic autogenerate/compare sees the full metadata. Order follows the dependency
chain: identity -> organization -> material -> knowledge -> tutor -> assessment ->
intelligence -> operations.
"""

from app.db.base import Base  # noqa: F401  (re-exported for Alembic autogenerate)
from app.models.assessment import (  # noqa: F401
    Assessment,
    Question,
    QuestionAttempt,
    QuestionConcept,
    Quiz,
    QuizAttempt,
    QuizQuestion,
)
from app.models.context import LearningContext  # noqa: F401
from app.models.enums import (  # noqa: F401
    AssessmentStatus,
    AttemptStatus,
    ConceptRelationType,
    Difficulty,
    EventType,
    ExtractionMethod,
    GrowthStatus,
    JobStatus,
    MasterySource,
    MasteryTrend,
    MaterialStatus,
    MaterialType,
    MessageRole,
    QuestionType,
    QuizStatus,
    RecommendationStatus,
    RecommendationType,
)
from app.models.evaluation import EvaluationResult, EvaluationRun  # noqa: F401
from app.models.intelligence import Growth, Mastery, MasteryHistory, Recommendation  # noqa: F401
from app.models.knowledge import Concept, ConceptRelationship  # noqa: F401
from app.models.learning import Project, Space  # noqa: F401
from app.models.materials import Document, DocumentChunk, Material  # noqa: F401
from app.models.observability import AiUsage  # noqa: F401
from app.models.ops import Event, ProcessingJob  # noqa: F401
from app.models.tutor import Conversation, Message  # noqa: F401
from app.models.users import User  # noqa: F401

__all__ = [
    "AiUsage",
    "Assessment",
    "Base",
    "Concept",
    "ConceptRelationship",
    "Conversation",
    "Document",
    "DocumentChunk",
    "EvaluationResult",
    "EvaluationRun",
    "Event",
    "Growth",
    "LearningContext",
    "Mastery",
    "MasteryHistory",
    "Material",
    "Message",
    "ProcessingJob",
    "Project",
    "Question",
    "QuestionAttempt",
    "QuestionConcept",
    "Quiz",
    "QuizAttempt",
    "QuizQuestion",
    "Recommendation",
    "Space",
    "User",
]
