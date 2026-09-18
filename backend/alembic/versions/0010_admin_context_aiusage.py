"""Admin RBAC + learning context + AI observability + evaluation persistence.

Revision ID: 0010_admin_context_aiusage
Revises: 0009_recommendation_dedup

- ``users.role`` (VARCHAR(16), default 'learner'): minimal learner/admin RBAC.
  Backfilled to 'learner' for existing rows (server_default covers it).
- ``learning_contexts``: one derived-state row per (user, project).
- ``ai_usage``: one row per recorded provider call (metadata only, no prompts).
- ``evaluation_runs`` / ``evaluation_results``: persisted eval outcomes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_admin_context_aiusage"
down_revision: str | None = "0009_recommendation_dedup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(16), nullable=False, server_default="learner"),
    )

    op.create_table(
        "learning_contexts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("learning_goal", sa.Text(), nullable=True),
        sa.Column("strengths", JSON, nullable=False, server_default="[]"),
        sa.Column("weaknesses", JSON, nullable=False, server_default="[]"),
        sa.Column("repeated_mistakes", JSON, nullable=False, server_default="[]"),
        sa.Column("notes", JSON, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "project_id", name="uq_learning_context_scope"),
    )
    op.create_index("ix_learning_contexts_user", "learning_contexts", ["user_id"])
    op.create_index("ix_learning_contexts_project", "learning_contexts", ["project_id"])

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("feature", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("error_type", sa.String(128), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_feature", "ai_usage", ["feature"])
    op.create_index("ix_ai_usage_user_created", "ai_usage", ["user_id", "created_at"])
    op.create_index("ix_ai_usage_project_created", "ai_usage", ["project_id", "created_at"])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("triggered_by_id", sa.Uuid(), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["triggered_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("case_id", sa.String(128), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("expected", sa.String(512), nullable=False, server_default=""),
        sa.Column("actual", sa.String(512), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evaluation_results_run", "evaluation_results", ["run_id"])
    op.create_index("ix_evaluation_results_category", "evaluation_results", ["category"])


def downgrade() -> None:
    op.drop_index("ix_evaluation_results_category", table_name="evaluation_results")
    op.drop_index("ix_evaluation_results_run", table_name="evaluation_results")
    op.drop_table("evaluation_results")
    op.drop_table("evaluation_runs")
    op.drop_index("ix_ai_usage_project_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_user_created", table_name="ai_usage")
    op.drop_index("ix_ai_usage_feature", table_name="ai_usage")
    op.drop_table("ai_usage")
    op.drop_index("ix_learning_contexts_project", table_name="learning_contexts")
    op.drop_index("ix_learning_contexts_user", table_name="learning_contexts")
    op.drop_table("learning_contexts")
    op.drop_column("users", "role")
