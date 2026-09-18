"""Persistent relevant learning context: one row per (user, project).

Only *derived, useful* state lives here — never raw conversation history.
Updated deterministically from assessment/mastery signals
(see LearningContextService); read back bounded for Tutor prompts.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import FlexibleJSON, TimestampMixin


class LearningContext(Base, TimestampMixin):
    """Relevant persistent learner state for one project.

    - ``strengths``/``weaknesses``: lists of {concept_id, concept_name, score}.
    - ``repeated_mistakes``: lists of {concept_id, concept_name, misses, window}.
    - ``notes``: small derived facts, e.g. assessment-derived observations.
    - ``learning_goal``: snapshot of the project goal at last update.
    """

    __tablename__ = "learning_contexts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learning_goal: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    strengths: Mapped[list[dict[str, Any]]] = mapped_column(
        FlexibleJSON, nullable=False, default=list
    )
    weaknesses: Mapped[list[dict[str, Any]]] = mapped_column(
        FlexibleJSON, nullable=False, default=list
    )
    repeated_mistakes: Mapped[list[dict[str, Any]]] = mapped_column(
        FlexibleJSON, nullable=False, default=list
    )
    notes: Mapped[list[str]] = mapped_column(FlexibleJSON, nullable=False, default=list)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "project_id", name="uq_learning_context_scope"),
    )
