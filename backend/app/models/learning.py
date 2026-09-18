"""Learning organization: Space (broad area) -> Project (central workspace).

Every project-owned entity in the system is traceable to its Project; repositories
expose scoped accessors (e.g. ``get_material_for_project``) so cross-project access
is impossible by construction. ``Project.owner_id`` is denormalized from Space for
O(1) authorization checks and kept consistent at creation time by the service layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import Difficulty
from app.models.mixins import FlexibleJSON, TimestampMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment, Question, Quiz, QuizAttempt
    from app.models.intelligence import Growth, Mastery, Recommendation
    from app.models.knowledge import Concept
    from app.models.materials import Document, DocumentChunk, Material
    from app.models.ops import Event, ProcessingJob
    from app.models.tutor import Conversation
    from app.models.users import User


class Space(Base, TimestampMixin):
    """A real parent entity for projects, not a label. Archive via ``archived_at``."""

    __tablename__ = "spaces"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    color: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    owner: Mapped[User] = relationship(back_populates="spaces")
    projects: Mapped[list[Project]] = relationship(
        back_populates="space", cascade="all, delete-orphan", passive_deletes=True
    )


class Project(Base, TimestampMixin):
    """Central learning workspace. Archived (not deleted) via ``archived_at``."""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    space_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(sa.String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    learning_goal: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    target_outcome: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    difficulty: Mapped[Difficulty | None] = mapped_column(
        sa.Enum(Difficulty, name="difficulty"), nullable=True
    )
    project_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", FlexibleJSON, nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (sa.Index("ix_projects_space_owner", "space_id", "owner_id"),)

    space: Mapped[Space] = relationship(back_populates="projects")
    owner: Mapped[User] = relationship(back_populates="projects")
    materials: Mapped[list[Material]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    concepts: Mapped[list[Concept]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    quizzes: Mapped[list[Quiz]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    questions: Mapped[list[Question]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    quiz_attempts: Mapped[list[QuizAttempt]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    mastery_records: Mapped[list[Mastery]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    growth_records: Mapped[list[Growth]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    recommendations: Mapped[list[Recommendation]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list[Event]] = relationship(back_populates="project", passive_deletes=True)
    processing_jobs: Mapped[list[ProcessingJob]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
