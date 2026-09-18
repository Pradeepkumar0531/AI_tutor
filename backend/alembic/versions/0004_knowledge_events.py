"""Knowledge-pipeline events: extend event_type with embedding/concept values.

Revision ID: 0004_knowledge_events
Revises: 0003_space_created_event

Same pattern as 0002/0003: PostgreSQL ALTER TYPE ... ADD VALUE cannot run inside
a transaction block, so it executes in an autocommit block and only on
PostgreSQL (SQLite stores enums as VARCHAR and needs nothing). Downgrade is
intentionally a no-op: PostgreSQL cannot drop enum values, and audit history
must never be rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_knowledge_events"
down_revision: str | None = "0003_space_created_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = (
    "EMBEDDING_STARTED",
    "EMBEDDING_COMPLETED",
    "EMBEDDING_FAILED",
    "CONCEPTS_EXTRACTED",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(sa.text(f"ALTER TYPE event_type ADD VALUE IF NOT EXISTS '{value}'"))


def downgrade() -> None:
    # No-op by design: PostgreSQL cannot remove enum values, and audit history
    # must never be rewritten. See module docstring.
    pass
