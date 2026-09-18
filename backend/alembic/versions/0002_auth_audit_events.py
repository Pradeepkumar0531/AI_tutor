"""Auth audit events: extend event_type with USER_* values.

Revision ID: 0002_auth_audit_events
Revises: 0001_initial_domain

PostgreSQL ALTER TYPE ... ADD VALUE cannot run inside a transaction block, so the
statements execute in an autocommit block and only on PostgreSQL (SQLite stores
enums as VARCHAR and needs nothing). Downgrade is intentionally a no-op:
PostgreSQL cannot drop enum values, and wiping history would destroy audit data.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_auth_audit_events"
down_revision: str | None = "0001_initial_domain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("USER_REGISTERED", "USER_LOGIN_SUCCEEDED", "USER_LOGIN_FAILED", "USER_LOGOUT")


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
