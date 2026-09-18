"""Recommendation deduplication guard.

Revision ID: 0009_recommendation_dedup
Revises: 0008_document_images

- ``uq_recommendations_active_scope`` on (user_id, project_id, concept_id,
  type, status): at most one row per lifecycle state for the same scope, so
  repeated refreshes cannot create duplicate ACTIVE recommendations even
  under races. Terminal rows (COMPLETED/DISMISSED/EXPIRED) never block
  regeneration because the status is part of the key; NULL concept ids stay
  distinct on both dialects.
- ``recommendations.source_assessment_id`` (nullable FK to assessments,
  SET NULL): which assessment triggered the recommendation (provenance for
  the "why now" behind refresh-driven generation).

SQLite needs batch mode for ADD CONSTRAINT; PostgreSQL alters in place.
Downgrade drops the constraint.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_recommendation_dedup"
down_revision: str | None = "0008_document_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recommendations",
        sa.Column("source_assessment_id", sa.Uuid(), nullable=True),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            "fk_recommendations_source_assessment",
            "recommendations",
            "assessments",
            ["source_assessment_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_unique_constraint(
            "uq_recommendations_active_scope",
            "recommendations",
            ["user_id", "project_id", "concept_id", "type", "status"],
        )
    else:
        with op.batch_alter_table("recommendations") as batch:
            batch.create_foreign_key(
                "fk_recommendations_source_assessment",
                "assessments",
                ["source_assessment_id"],
                ["id"],
                ondelete="SET NULL",
            )
            batch.create_unique_constraint(
                "uq_recommendations_active_scope",
                ["user_id", "project_id", "concept_id", "type", "status"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint(
            "fk_recommendations_source_assessment", "recommendations", type_="foreignkey"
        )
        op.drop_constraint("uq_recommendations_active_scope", "recommendations", type_="unique")
        op.drop_column("recommendations", "source_assessment_id")
    else:
        with op.batch_alter_table("recommendations") as batch:
            batch.drop_constraint("fk_recommendations_source_assessment", type_="foreignkey")
            batch.drop_constraint("uq_recommendations_active_scope", type_="unique")
            batch.drop_column("source_assessment_id")
