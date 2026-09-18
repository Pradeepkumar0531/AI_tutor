"""Assessment engine: QuestionConcept project isolation, quiz idempotency key,
assessment concept results, quiz-created event.

Revision ID: 0006_assessment_engine
Revises: 0005_tutor_conversations

- ``question_concepts.project_id`` (NOT NULL, backfilled from the linked
  question) plus composite FKs ``fk_qc_question_in_project`` /
  ``fk_qc_concept_in_project``: the database itself guarantees
  ``Question.project_id == QuestionConcept.project_id == Concept.project_id``
  (same pattern as ``ConceptRelationship``). The older single-column FKs are
  retained; the composite ones are the authority. SQLite needs batch mode for
  the NOT NULL + FK changes; PostgreSQL alters in place.
- ``quizzes.client_request_key`` + ``uq_quizzes_project_client_key``: retried
  quiz-creation POSTs with the same key resolve to the original quiz instead
  of generating duplicates (NULL keys stay distinct on both dialects).
- ``assessments.concept_results`` (JSONB, nullable): immutable per-concept
  snapshot written once at completion for Prompt 9's Mastery engine.
- Extends ``event_type`` with ``QUIZ_CREATED`` (same autocommit-block
  PostgreSQL-only pattern as 0002–0005).

Downgrade drops the added columns/constraints; enum values are intentionally
left in place (PostgreSQL cannot drop enum values, and audit history must
never be rewritten).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_assessment_engine"
down_revision: str | None = "0005_tutor_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("QUIZ_CREATED",)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.add_column("quizzes", sa.Column("client_request_key", sa.String(64), nullable=True))
        op.create_unique_constraint(
            "uq_quizzes_project_client_key", "quizzes", ["project_id", "client_request_key"]
        )
        op.add_column(
            "assessments", sa.Column("concept_results", postgresql.JSONB(), nullable=True)
        )
        op.create_unique_constraint("uq_questions_project_id", "questions", ["project_id", "id"])
    else:
        # SQLite cannot ALTER constraints outside batch (copy-and-move) mode.
        with op.batch_alter_table("quizzes") as batch:
            batch.add_column(sa.Column("client_request_key", sa.String(64), nullable=True))
            batch.create_unique_constraint(
                "uq_quizzes_project_client_key", ["project_id", "client_request_key"]
            )
        with op.batch_alter_table("assessments") as batch:
            # sa.JSON on SQLite (batch mode strictly compiles column types and
            # cannot render postgresql.JSONB); PostgreSQL branch uses JSONB.
            batch.add_column(sa.Column("concept_results", sa.JSON(), nullable=True))
        with op.batch_alter_table("questions") as batch:
            batch.create_unique_constraint("uq_questions_project_id", ["project_id", "id"])

    op.add_column("question_concepts", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE question_concepts SET project_id = "
            "(SELECT project_id FROM questions WHERE questions.id = question_concepts.question_id) "
            "WHERE project_id IS NULL"
        )
    )
    if bind.dialect.name == "postgresql":
        op.alter_column("question_concepts", "project_id", nullable=False)
        op.create_foreign_key(
            "fk_qc_question_in_project",
            "question_concepts",
            "questions",
            ["project_id", "question_id"],
            ["project_id", "id"],
            ondelete="CASCADE",
        )
        op.create_foreign_key(
            "fk_qc_concept_in_project",
            "question_concepts",
            "concepts",
            ["project_id", "concept_id"],
            ["project_id", "id"],
            ondelete="CASCADE",
        )
    else:
        with op.batch_alter_table("question_concepts") as batch:
            batch.alter_column("project_id", nullable=False)
            batch.create_foreign_key(
                "fk_qc_question_in_project",
                "questions",
                ["project_id", "question_id"],
                ["project_id", "id"],
                ondelete="CASCADE",
            )
            batch.create_foreign_key(
                "fk_qc_concept_in_project",
                "concepts",
                ["project_id", "concept_id"],
                ["project_id", "id"],
                ondelete="CASCADE",
            )

    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(sa.text(f"ALTER TYPE event_type ADD VALUE IF NOT EXISTS '{value}'"))


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint("fk_qc_concept_in_project", "question_concepts", type_="foreignkey")
        op.drop_constraint("fk_qc_question_in_project", "question_concepts", type_="foreignkey")
        op.alter_column("question_concepts", "project_id", nullable=True)
        op.drop_column("question_concepts", "project_id")
        op.drop_constraint("uq_questions_project_id", "questions", type_="unique")
        op.drop_column("assessments", "concept_results")
        op.drop_constraint("uq_quizzes_project_client_key", "quizzes", type_="unique")
        op.drop_column("quizzes", "client_request_key")
    else:
        with op.batch_alter_table("question_concepts") as batch:
            batch.drop_constraint("fk_qc_concept_in_project", type_="foreignkey")
            batch.drop_constraint("fk_qc_question_in_project", type_="foreignkey")
            batch.alter_column("project_id", nullable=True)
        with op.batch_alter_table("question_concepts") as batch:
            batch.drop_column("project_id")
        with op.batch_alter_table("questions") as batch:
            batch.drop_constraint("uq_questions_project_id", type_="unique")
        with op.batch_alter_table("assessments") as batch:
            batch.drop_column("concept_results")
        with op.batch_alter_table("quizzes") as batch:
            batch.drop_constraint("uq_quizzes_project_client_key", type_="unique")
            batch.drop_column("client_request_key")
