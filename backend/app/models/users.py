"""User identity model. Authentication material only — no tokens, no API keys."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.learning import Project, Space


class User(Base, TimestampMixin):
    """Application user. Email is unique and always stored normalized (lowercased).

    Deleting a user cascades to owned spaces/projects (GDPR-friendly cleanup).
    See docs/DATABASE.md for the deletion policy.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(sa.String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    # Minimal RBAC: 'learner' or 'admin'. Plain string (not a PG enum) so role
    # checks stay a simple equality; see docs/ADMIN.md.
    role: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, default="learner", server_default="learner"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    spaces: Mapped[list[Space]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )
    projects: Mapped[list[Project]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", passive_deletes=True
    )

    @staticmethod
    def normalize_email(raw: str) -> str:
        """Canonical email form: trimmed + lowercased. Applied on every write path."""
        return raw.strip().lower()
