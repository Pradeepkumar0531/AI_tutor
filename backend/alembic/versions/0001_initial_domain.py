"""Initial domain schema: full learning-platform model on PostgreSQL + pgvector.

Revision ID: 0001_initial_domain
Revises: None
Create Date: 2026-09-16

Covers: users, spaces, projects, materials, documents, document_chunks (Vector(768)
for Google text-embedding-004), concepts, concept_relationships, conversations,
messages, quizzes, questions, quiz_questions, question_concepts, quiz_attempts,
question_attempts, assessments, mastery, mastery_history, growth, recommendations,
events, processing_jobs.

Safe direction: upgrade is additive (CREATE EXTENSION IF NOT EXISTS + CREATEs).
Downgrade drops tables and enum types in reverse dependency order; the ``vector``
extension is intentionally left installed (shared cluster resource).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.enums import (
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

revision: str = "0001_initial_domain"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = sa.text("now()")

ENUMS: list[tuple[type, str]] = [
    (MaterialType, "material_type"),
    (MaterialStatus, "material_status"),
    (ExtractionMethod, "extraction_method"),
    (MessageRole, "message_role"),
    (Difficulty, "difficulty"),
    (QuizStatus, "quiz_status"),
    (QuestionType, "question_type"),
    (AttemptStatus, "attempt_status"),
    (AssessmentStatus, "assessment_status"),
    (MasteryTrend, "mastery_trend"),
    (MasterySource, "mastery_source"),
    (GrowthStatus, "growth_status"),
    (RecommendationType, "recommendation_type"),
    (RecommendationStatus, "recommendation_status"),
    (ConceptRelationType, "concept_relation_type"),
    (JobStatus, "job_status"),
    (EventType, "event_type"),
]


def _E(py_enum, name):
    """Non-creating enum reference for table columns.

    All enum types are created exactly once, up front, with checkfirst=True
    (see upgrade()). Column definitions must NOT re-emit CREATE TYPE, or the
    second table using the same enum fails on PostgreSQL with
    DuplicateObject. (SQLite renders enums as VARCHAR, which is why this only
    ever broke live Postgres upgrades. Note: create_type exists only on the
    postgresql.ENUM dialect type, not on generic sa.Enum.)
    """
    return postgresql.ENUM(py_enum, name=name, create_type=False)


def _timestamps(with_updated: bool = True) -> list[sa.Column]:
    cols = [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW)
    ]
    if with_updated:
        cols.append(
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW)
        )
    return cols


def upgrade() -> None:
    op.execute(sa.text('CREATE EXTENSION IF NOT EXISTS "vector"'))
    for py_enum, name in ENUMS:
        sa.Enum(py_enum, name=name).create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "spaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(64), nullable=True),
        sa.Column("color", sa.String(16), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_spaces_owner_id", "spaces", ["owner_id"])

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("space_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("learning_goal", sa.Text(), nullable=True),
        sa.Column("target_outcome", sa.Text(), nullable=True),
        sa.Column("difficulty", _E(Difficulty, "difficulty"), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_space_id", "projects", ["space_id"])
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_index("ix_projects_space_owner", "projects", ["space_id", "owner_id"])

    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", _E(MaterialType, "material_type"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", _E(MaterialStatus, "material_status"), nullable=False),
        sa.Column("storage_provider", sa.String(32), nullable=False, server_default="local"),
        sa.Column("storage_key", sa.String(512), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("mime_type", sa.String(128), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("file_size IS NULL OR file_size >= 0", name="ck_materials_file_size"),
        sa.CheckConstraint("retry_count >= 0", name="ck_materials_retry_count"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_materials_project_id", "materials", ["project_id"])
    op.create_index("ix_materials_status", "materials", ["status"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_method", _E(ExtractionMethod, "extraction_method"), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("page_count IS NULL OR page_count >= 0", name="ck_documents_pages"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("material_id", name="uq_documents_material_id"),
    )
    op.create_index("ix_documents_project_id", "documents", ["project_id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("section_title", sa.String(255), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(768), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("chunk_index >= 0", name="ck_chunks_index"),
        sa.CheckConstraint("page_start IS NULL OR page_start >= 0", name="ck_chunks_page_start"),
        sa.CheckConstraint("token_count IS NULL OR token_count >= 0", name="ck_chunks_tokens"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_project_id", "document_chunks", ["project_id"])

    op.create_table(
        "concepts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("difficulty", _E(Difficulty, "difficulty"), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "id", name="uq_concepts_project_id"),
        sa.UniqueConstraint("project_id", "normalized_name", name="uq_concepts_project_normalized"),
    )
    op.create_index("ix_concepts_project_id", "concepts", ["project_id"])

    op.create_table(
        "concept_relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("source_concept_id", sa.Uuid(), nullable=False),
        sa.Column("target_concept_id", sa.Uuid(), nullable=False),
        sa.Column(
            "relationship_type",
            _E(ConceptRelationType, "concept_relation_type"),
            nullable=False,
        ),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("source_concept_id != target_concept_id", name="ck_rel_no_self_link"),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_rel_weight_bounds"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "source_concept_id"],
            ["concepts.project_id", "concepts.id"],
            ondelete="CASCADE",
            name="fk_rel_source_in_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "target_concept_id"],
            ["concepts.project_id", "concepts.id"],
            ondelete="CASCADE",
            name="fk_rel_target_in_project",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_concept_id", "target_concept_id", "relationship_type", name="uq_rel_directional"
        ),
    )
    op.create_index("ix_concept_relationships_project_id", "concept_relationships", ["project_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False, server_default="New conversation"),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_conversations_project_user", "conversations", ["project_id", "user_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", _E(MessageRole, "message_role"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(), nullable=True),
        sa.Column("retrieval_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_messages_latency"),
        sa.CheckConstraint(
            "retrieval_count IS NULL OR retrieval_count >= 0", name="ck_messages_retrieval"
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )

    op.create_table(
        "quizzes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", _E(QuizStatus, "quiz_status"), nullable=False),
        sa.Column("difficulty", _E(Difficulty, "difficulty"), nullable=True),
        sa.Column("generated_by_ai", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("generation_metadata", postgresql.JSONB(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quizzes_project_id", "quizzes", ["project_id"])
    op.create_index("ix_quizzes_status", "quizzes", ["status"])

    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("type", _E(QuestionType, "question_type"), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("difficulty", _E(Difficulty, "difficulty"), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("correct_answer", sa.Text(), nullable=True),
        sa.Column("options", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_questions_project_id", "questions", ["project_id"])
    op.create_index("ix_questions_type", "questions", ["type"])

    op.create_table(
        "quiz_questions",
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("points", sa.Float(), nullable=False, server_default="1.0"),
        sa.CheckConstraint("position >= 0", name="ck_quizq_position"),
        sa.CheckConstraint("points >= 0", name="ck_quizq_points"),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("quiz_id", "question_id"),
        sa.UniqueConstraint("quiz_id", "position", name="uq_quiz_position"),
    )
    op.create_index("ix_quiz_questions_question_id", "quiz_questions", ["question_id"])

    op.create_table(
        "question_concepts",
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_qc_weight"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("question_id", "concept_id"),
    )
    op.create_index("ix_question_concepts_concept_id", "question_concepts", ["concept_id"])

    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quiz_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("status", _E(AttemptStatus, "attempt_status"), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("max_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("score IS NULL OR score >= 0", name="ck_attempt_score"),
        sa.CheckConstraint("max_score IS NULL OR max_score >= 0", name="ck_attempt_max"),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at", name="ck_attempt_order"
        ),
        sa.ForeignKeyConstraint(["quiz_id"], ["quizzes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quiz_attempts_quiz_id", "quiz_attempts", ["quiz_id"])
    op.create_index("ix_quiz_attempts_user_id", "quiz_attempts", ["user_id"])
    op.create_index("ix_quiz_attempts_project_id", "quiz_attempts", ["project_id"])
    op.create_index("ix_quiz_attempts_status", "quiz_attempts", ["status"])

    op.create_table(
        "question_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("quiz_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("evaluation", postgresql.JSONB(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("score IS NULL OR score >= 0", name="ck_qattempt_score"),
        sa.ForeignKeyConstraint(["quiz_attempt_id"], ["quiz_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quiz_attempt_id", "question_id", name="uq_attempt_question_once"),
    )
    op.create_index(
        "ix_question_attempts_quiz_attempt_id", "question_attempts", ["quiz_attempt_id"]
    )
    op.create_index("ix_question_attempts_question_id", "question_attempts", ["question_id"])

    op.create_table(
        "assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("quiz_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("status", _E(AssessmentStatus, "assessment_status"), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)", name="ck_assessment_score"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quiz_attempt_id"], ["quiz_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quiz_attempt_id", name="uq_assessments_quiz_attempt"),
    )
    op.create_index("ix_assessments_project_id", "assessments", ["project_id"])
    op.create_index("ix_assessments_user_id", "assessments", ["user_id"])
    op.create_index("ix_assessments_status", "assessments", ["status"])

    op.create_table(
        "mastery",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("trend", _E(MasteryTrend, "mastery_trend"), nullable=False),
        sa.Column("last_assessed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_mastery_score"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_mastery_confidence"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "project_id", "concept_id", name="uq_mastery_user_project_concept"
        ),
    )
    op.create_index("ix_mastery_project_id", "mastery", ["project_id"])
    op.create_index("ix_mastery_user_id", "mastery", ["user_id"])
    op.create_index("ix_mastery_concept_id", "mastery", ["concept_id"])
    op.create_index("ix_mastery_project_user", "mastery", ["project_id", "user_id"])

    op.create_table(
        "mastery_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mastery_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("source", _E(MasterySource, "mastery_source"), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_mhistory_score"),
        sa.ForeignKeyConstraint(["mastery_id"], ["mastery.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mastery_history_mastery_id", "mastery_history", ["mastery_id"])
    op.create_index("ix_mastery_history_assessment_id", "mastery_history", ["assessment_id"])
    op.create_index(
        "ix_mastery_history_mastery_created",
        "mastery_history",
        ["mastery_id", "created_at"],
    )

    op.create_table(
        "growth",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=False),
        sa.Column("status", _E(GrowthStatus, "growth_status"), nullable=False),
        sa.Column("change_score", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "project_id", "concept_id", name="uq_growth_user_project_concept"
        ),
    )
    op.create_index("ix_growth_project_id", "growth", ["project_id"])
    op.create_index("ix_growth_user_id", "growth", ["user_id"])
    op.create_index("ix_growth_concept_id", "growth", ["concept_id"])
    op.create_index("ix_growth_status", "growth", ["status"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("concept_id", sa.Uuid(), nullable=True),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("type", _E(RecommendationType, "recommendation_type"), nullable=False),
        sa.Column("status", _E(RecommendationStatus, "recommendation_status"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("priority >= 0", name="ck_recommendation_priority"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["concept_id"], ["concepts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendations_project_id", "recommendations", ["project_id"])
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])
    op.create_index("ix_recommendations_concept_id", "recommendations", ["concept_id"])
    op.create_index("ix_recommendations_material_id", "recommendations", ["material_id"])
    op.create_index("ix_recommendations_status", "recommendations", ["status"])
    op.create_index(
        "ix_recommendations_project_status", "recommendations", ["project_id", "status"]
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", _E(EventType, "event_type"), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_events_user_id", "events", ["user_id"])
    op.create_index("ix_events_project_id", "events", ["project_id"])
    op.create_index("ix_events_event_type", "events", ["event_type"])
    op.create_index("ix_events_project_created", "events", ["project_id", "created_at"])

    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("material_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", _E(JobStatus, "job_status"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("attempt_count >= 0", name="ck_jobs_attempts"),
        sa.CheckConstraint("max_retries >= 0", name="ck_jobs_max_retries"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_processing_jobs_idempotency_key"),
    )
    op.create_index("ix_processing_jobs_material_id", "processing_jobs", ["material_id"])
    op.create_index("ix_processing_jobs_project_id", "processing_jobs", ["project_id"])
    op.create_index("ix_processing_jobs_status", "processing_jobs", ["status"])


def downgrade() -> None:
    for table in [
        "processing_jobs",
        "events",
        "recommendations",
        "growth",
        "mastery_history",
        "mastery",
        "assessments",
        "question_attempts",
        "quiz_attempts",
        "question_concepts",
        "quiz_questions",
        "questions",
        "quizzes",
        "messages",
        "conversations",
        "concept_relationships",
        "concepts",
        "document_chunks",
        "documents",
        "materials",
        "projects",
        "spaces",
        "users",
    ]:
        op.drop_table(table)
    for _, name in reversed(ENUMS):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
    # NOTE: the `vector` extension is deliberately left installed.
