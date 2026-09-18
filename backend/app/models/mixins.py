"""Shared column building blocks: UUID PKs, UTC timestamps, portable JSONB.

Conventions (see docs/DATABASE.md):
- Primary keys: UUID, generated application-side via ``uuid.uuid4`` unless the database
  supplies one. ``sa.Uuid`` renders native UUID on PostgreSQL, CHAR(32) on SQLite.
- Timestamps: timezone-aware UTC. ORM-side default (aware ``datetime``) with
  ``server_default=func.now()`` as a backstop for raw SQL writes.
- Flexible metadata: JSONB on PostgreSQL, plain JSON on SQLite via ``with_variant``.
  Reserved for genuinely schemaless data (payloads, options, observability) — never as
  a substitute for relational modeling.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

# Embedding model: Google `models/gemini-embedding-001` -> fixed 768 dimensions.
# Changing the embedding model requires an explicit migration that rewrites this
# column; dimensions must never be silently mixed (see docs/DATABASE.md).
EMBEDDING_DIMENSIONS = 768

FlexibleJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """created_at/updated_at for mutable entities."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
    )


class CreatedMixin:
    """created_at only for append-only / immutable entities (events, attempts...)."""

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
