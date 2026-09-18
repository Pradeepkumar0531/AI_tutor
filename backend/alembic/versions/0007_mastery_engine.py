"""Mastery engine persistence: previous-score provenance and idempotency.

Revision ID: 0007_mastery_engine
Revises: 0006_assessment_engine

- ``mastery_history.previous_score`` (nullable float): the 0-100 mastery
  score before the observation, so every transition (previous -> new) is
  explainable from stored rows. NULL for pre-Prompt-9 rows.
- ``uq_mastery_history_mastery_assessment`` on (mastery_id, assessment_id):
  the idempotency guard — reprocessing the same assessment for the same
  concept cannot duplicate history (NULL assessment ids stay distinct on
  both dialects, preserving manual observations).
- Check constraint ``ck_mhistory_previous_score`` keeps the new column in
  the 0-100 mastery scale.

SQLite needs batch mode for ADD CONSTRAINT; PostgreSQL alters in place.
Downgrade drops the additions; audit history rows are never rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_mastery_engine"
down_revision: str | None = "0006_assessment_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mastery_history", sa.Column("previous_score", sa.Float(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_mhistory_previous_score",
            "mastery_history",
            "previous_score IS NULL OR (previous_score >= 0 AND previous_score <= 100)",
        )
        op.create_unique_constraint(
            "uq_mastery_history_mastery_assessment",
            "mastery_history",
            ["mastery_id", "assessment_id"],
        )
    else:
        with op.batch_alter_table("mastery_history") as batch:
            batch.create_check_constraint(
                "ck_mhistory_previous_score",
                "previous_score IS NULL OR (previous_score >= 0 AND previous_score <= 100)",
            )
            batch.create_unique_constraint(
                "uq_mastery_history_mastery_assessment", ["mastery_id", "assessment_id"]
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint(
            "uq_mastery_history_mastery_assessment", "mastery_history", type_="unique"
        )
        op.drop_constraint("ck_mhistory_previous_score", "mastery_history", type_="check")
        op.drop_column("mastery_history", "previous_score")
    else:
        with op.batch_alter_table("mastery_history") as batch:
            batch.drop_constraint("uq_mastery_history_mastery_assessment", type_="unique")
            batch.drop_constraint("ck_mhistory_previous_score", type_="check")
            batch.drop_column("previous_score")
