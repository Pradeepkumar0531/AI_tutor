"""Assessment chain: Quiz -< QuizQuestion >- Question -< QuestionConcept >- Concept,
plus the interaction/session layer (QuizAttempt -> QuestionAttempt) and the
interpreted-evaluation layer (Assessment).

QuizAttempt vs Assessment (deliberate split):
- QuizAttempt = the interaction session (user answers questions, scores accumulate).
- Assessment = the interpreted learning evaluation derived from (usually one) quiz
  attempt. It is what feeds Mastery/Growth/Recommendations, so evaluation semantics
  can evolve without rewriting session history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    AssessmentStatus,
    AttemptStatus,
    Difficulty,
    QuestionType,
    QuizStatus,
)
from app.models.mixins import CreatedMixin, FlexibleJSON, TimestampMixin, utcnow

if TYPE_CHECKING:
    from app.models.learning import Project
    from app.models.users import User


class Quiz(Base, TimestampMixin):
    __tablename__ = "quizzes"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[QuizStatus] = mapped_column(
        sa.Enum(QuizStatus, name="quiz_status"),
        nullable=False,
        default=QuizStatus.DRAFT,
        index=True,
    )
    difficulty: Mapped[Difficulty | None] = mapped_column(
        sa.Enum(Difficulty, name="difficulty"), nullable=True
    )
    generated_by_ai: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    generation_metadata: Mapped[dict[str, Any] | None] = mapped_column(FlexibleJSON, nullable=True)
    # Client-supplied idempotency key: retried POSTs with the same key return
    # the original quiz instead of generating a duplicate. NULL = no key.
    client_request_key: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "project_id", "client_request_key", name="uq_quizzes_project_client_key"
        ),
    )

    project: Mapped[Project] = relationship(back_populates="quizzes")
    quiz_questions: Mapped[list[QuizQuestion]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="QuizQuestion.position",
    )
    attempts: Mapped[list[QuizAttempt]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", passive_deletes=True
    )


class Question(Base, TimestampMixin):
    """Project-scoped question bank entry. MCQ options live in ``options`` JSONB
    (a list of ``{"key": ..., "text": ...}`` objects) — never option_a/b/c/d columns."""

    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[QuestionType] = mapped_column(
        sa.Enum(QuestionType, name="question_type"), nullable=False, index=True
    )
    prompt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    difficulty: Mapped[Difficulty | None] = mapped_column(
        sa.Enum(Difficulty, name="difficulty"), nullable=True
    )
    explanation: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    correct_answer: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    options: Mapped[list[Any] | None] = mapped_column(FlexibleJSON, nullable=True)
    question_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", FlexibleJSON, nullable=True
    )

    __table_args__ = (
        # Anchor for the QuestionConcept composite FKs below: a concept link
        # can only reference a question through its own project.
        sa.UniqueConstraint("project_id", "id", name="uq_questions_project_id"),
    )

    project: Mapped[Project] = relationship(back_populates="questions")
    quiz_questions: Mapped[list[QuizQuestion]] = relationship(
        back_populates="question", passive_deletes=True
    )
    concepts: Mapped[list[QuestionConcept]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="QuestionConcept.question_id",
    )


class QuizQuestion(Base):
    """Join: a question's placement inside a quiz. Composite PK enforces one
    placement per (quiz, question); ``uq_quiz_position`` keeps ordering total."""

    __tablename__ = "quiz_questions"

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("quizzes.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    points: Mapped[float] = mapped_column(sa.Float, nullable=False, default=1.0)

    __table_args__ = (
        sa.UniqueConstraint("quiz_id", "position", name="uq_quiz_position"),
        sa.CheckConstraint("position >= 0", name="ck_quizq_position"),
        sa.CheckConstraint("points >= 0", name="ck_quizq_points"),
    )

    quiz: Mapped[Quiz] = relationship(back_populates="quiz_questions")
    question: Mapped[Question] = relationship(back_populates="quiz_questions")


class QuestionConcept(Base):
    """Join: Question -> Concept -> Mastery path for adaptive assessment.

    Project isolation is enforced at the database level: the composite FKs
    below guarantee ``Question.project_id == QuestionConcept.project_id ==
    Concept.project_id`` (same pattern as ``ConceptRelationship``). The older
    single-column FKs are retained for compatibility; the composite ones are
    the authority.
    """

    __tablename__ = "question_concepts"

    question_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("questions.id", ondelete="CASCADE"), primary_key=True
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("concepts.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weight: Mapped[float] = mapped_column(sa.Float, nullable=False, default=1.0)
    is_primary: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["project_id", "question_id"],
            ["questions.project_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_qc_question_in_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "concept_id"],
            ["concepts.project_id", "concepts.id"],
            ondelete="CASCADE",
            name="fk_qc_concept_in_project",
        ),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_qc_weight"),
    )

    question: Mapped[Question] = relationship(back_populates="concepts", foreign_keys=[question_id])


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[AttemptStatus] = mapped_column(
        sa.Enum(AttemptStatus, name="attempt_status"),
        nullable=False,
        default=AttemptStatus.IN_PROGRESS,
        index=True,
    )
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        sa.CheckConstraint("score IS NULL OR score >= 0", name="ck_attempt_score"),
        sa.CheckConstraint("max_score IS NULL OR max_score >= 0", name="ck_attempt_max"),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at", name="ck_attempt_order"
        ),
    )

    quiz: Mapped[Quiz] = relationship(back_populates="attempts")
    project: Mapped[Project] = relationship(back_populates="quiz_attempts")
    user: Mapped[User] = relationship()
    question_attempts: Mapped[list[QuestionAttempt]] = relationship(
        back_populates="quiz_attempt",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    assessment: Mapped[Assessment | None] = relationship(
        back_populates="quiz_attempt",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )


class QuestionAttempt(Base, CreatedMixin):
    __tablename__ = "question_attempts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    quiz_attempt_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # RESTRICT: historical answers must survive question-bank edits.
    question_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    answer: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    feedback: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # Open-ended AI evaluation breakdown stays schemaless; aggregates stay columns.
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(FlexibleJSON, nullable=True)
    answered_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.func.now(),
    )

    __table_args__ = (
        sa.UniqueConstraint("quiz_attempt_id", "question_id", name="uq_attempt_question_once"),
        sa.CheckConstraint("score IS NULL OR score >= 0", name="ck_qattempt_score"),
    )

    quiz_attempt: Mapped[QuizAttempt] = relationship(back_populates="question_attempts")


class Assessment(Base, CreatedMixin):
    __tablename__ = "assessments"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=True,
        unique=True,
    )
    status: Mapped[AssessmentStatus] = mapped_column(
        sa.Enum(AssessmentStatus, name="assessment_status"),
        nullable=False,
        default=AssessmentStatus.PENDING,
        index=True,
    )
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=sa.func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # Immutable per-concept snapshot for Prompt 9's Mastery engine: a list of
    # {concept_id, concept_name, questions_seen, correct_count, partial_count,
    # incorrect_count, normalized_score}. Derived at completion, never edited.
    concept_results: Mapped[list[Any] | None] = mapped_column(FlexibleJSON, nullable=True)

    __table_args__ = (
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)", name="ck_assessment_score"
        ),
    )

    project: Mapped[Project] = relationship(back_populates="assessments")
    user: Mapped[User] = relationship()
    quiz_attempt: Mapped[QuizAttempt | None] = relationship(back_populates="assessment")
