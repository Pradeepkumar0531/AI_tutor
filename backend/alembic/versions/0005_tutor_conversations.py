"""Tutor conversations: message idempotency key, citation persistence, events.

Revision ID: 0005_tutor_conversations
Revises: 0004_knowledge_events

- Adds ``messages.request_key`` (nullable, unique): client-generated UUIDs let
  retried sends resolve to the already-persisted user message instead of
  duplicating it. NULLs stay distinct on both PostgreSQL and SQLite.
- Adds ``messages.citations`` (JSONB, nullable): application-constructed
  citation objects persisted with the assistant message so retries/history
  replay identical provenance without re-deriving it.
- Adds ``messages.tutor_metadata`` (JSONB, nullable): question kind,
  insufficient-evidence flag, top similarity, retrieval latency.
- Extends ``event_type`` with ``CONVERSATION_CREATED`` / ``TUTOR_RESPONSE``
  (same autocommit-block pattern as 0002–0004).

Downgrade drops the columns/index; enum values are intentionally left in place
(PostgreSQL cannot drop enum values, and audit history must never be rewritten).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_tutor_conversations"
down_revision: str | None = "0004_knowledge_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = (
    "CONVERSATION_CREATED",
    "TUTOR_RESPONSE",
)


def upgrade() -> None:
    op.add_column("messages", sa.Column("request_key", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_messages_request_key", "messages", ["request_key"])
    op.add_column("messages", sa.Column("citations", postgresql.JSONB(), nullable=True))
    op.add_column("messages", sa.Column("tutor_metadata", postgresql.JSONB(), nullable=True))
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(sa.text(f"ALTER TYPE event_type ADD VALUE IF NOT EXISTS '{value}'"))


def downgrade() -> None:
    op.drop_constraint("uq_messages_request_key", "messages", type_="unique")
    op.drop_column("messages", "tutor_metadata")
    op.drop_column("messages", "citations")
    op.drop_column("messages", "request_key")
