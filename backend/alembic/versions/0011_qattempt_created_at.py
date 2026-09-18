"""Align question_attempts with the model (missing created_at).

Revision ID: 0011_qattempt_created_at
Revises: 0010_admin_context_aiusage

The model gained CreatedMixin after 0001 without a migration. ORM inserts
survived via the Python-side default, but the column was absent in
PostgreSQL. Adds it nullable-first with backfill, then NOT NULL with a
server default. (Index/constraint name drift reported by autogenerate is
cosmetic and intentionally left alone.)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_qattempt_created_at"
down_revision: str | None = "0010_admin_context_aiusage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "question_attempts",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(sa.text("UPDATE question_attempts SET created_at = now() WHERE created_at IS NULL"))
    op.alter_column("question_attempts", "created_at", nullable=False, server_default=sa.func.now())


def downgrade() -> None:
    op.drop_column("question_attempts", "created_at")
