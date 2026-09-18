"""Space lifecycle event: extend event_type with SPACE_CREATED.

Revision ID: 0003_space_created_event
Revises: 0002_auth_audit_events

Same pattern as 0002: PostgreSQL ALTER TYPE ... ADD VALUE cannot run inside a
transaction block, so it executes in an autocommit block and only on PostgreSQL
(SQLite stores enums as VARCHAR and needs nothing). Downgrade is intentionally
a no-op: PostgreSQL cannot drop enum values, and audit history must never be
rewritten.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_space_created_event"
down_revision: str | None = "0002_auth_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("SPACE_CREATED",)


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
