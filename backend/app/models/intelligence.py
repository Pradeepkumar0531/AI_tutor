"""Learning intelligence: Mastery (source of truth) + MasteryHistory (append-only
observations) + Growth (derived interpretation) + Recommendation (actionable links).

Direction of derivation: Assessment/Quiz/Tutor observations -> MasteryHistory rows ->
current Mastery row -> Growth summary. Growth never writes Mastery.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import (
    GrowthStatus,
    MasterySource,
    MasteryTrend,
    RecommendationStatus,
    RecommendationType,
)
from app.models.mixins import CreatedMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment
    from app.models.knowledge import Concept
    from app.models.learning import Project
    from app.models.materials import Material
    from app.models.users import User


class Mastery(Base, TimestampMixin):
    """Current concept mastery for one (user, project, concept). Score is 0-100."""

    __tablename__ = "mastery"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    trend: Mapped[MasteryTrend] = mapped_column(
        sa.Enum(MasteryTrend, name="mastery_trend"),
        nullable=False,
        default=MasteryTrend.STABLE,
    )
    last_assessed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "project_id", "concept_id", name="uq_mastery_user_project_concept"
        ),
        sa.Index("ix_mastery_project_user", "project_id", "user_id"),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_mastery_score"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_mastery_confidence"),
    )

    project: Mapped[Project] = relationship(back_populates="mastery_records")
    user: Mapped[User] = relationship()
    concept: Mapped[Concept] = relationship()
    history: Mapped[list[MasteryHistory]] = relationship(
        back_populates="mastery",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MasteryHistory.created_at",
    )


class MasteryHistory(Base, CreatedMixin):
    """Immutable observation that moved a Mastery row. History is never updated."""

    __tablename__ = "mastery_history"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    mastery_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("mastery.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    confidence: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    source: Mapped[MasterySource] = mapped_column(
        sa.Enum(MasterySource, name="mastery_source"), nullable=False
    )
    # SET NULL: observations outlive any single assessment record.
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Mastery score (0-100 scale, like Mastery.score) BEFORE this observation.
    # NULL for rows predating Prompt 9 or without a prior estimate.
    previous_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    __table_args__ = (
        sa.Index("ix_mastery_history_mastery_created", "mastery_id", "created_at"),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_mhistory_score"),
        sa.CheckConstraint(
            "previous_score IS NULL OR (previous_score >= 0 AND previous_score <= 100)",
            name="ck_mhistory_previous_score",
        ),
        # Idempotency: one history row per (mastery, assessment). Rows without
        # a source assessment (NULL) stay distinct on both dialects.
        sa.UniqueConstraint(
            "mastery_id", "assessment_id", name="uq_mastery_history_mastery_assessment"
        ),
    )

    mastery: Mapped[Mastery] = relationship(back_populates="history")
    assessment: Mapped[Assessment | None] = relationship()


class Growth(Base, TimestampMixin):
    """Derived progress interpretation over a (user, project, concept). Refreshed in
    place — one row per triple, backed by MasteryHistory, never the reverse."""

    __tablename__ = "growth"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concept_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("concepts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[GrowthStatus] = mapped_column(
        sa.Enum(GrowthStatus, name="growth_status"), nullable=False, index=True
    )
    change_score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint(
            "user_id", "project_id", "concept_id", name="uq_growth_user_project_concept"
        ),
    )

    project: Mapped[Project] = relationship(back_populates="growth_records")
    user: Mapped[User] = relationship()
    concept: Mapped[Concept] = relationship()


class Recommendation(Base, TimestampMixin):
    """Actionable link: weak concept + relevant material + recommended action."""

    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("concepts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("materials.id", ondelete="SET NULL"), nullable=True, index=True
    )
    type: Mapped[RecommendationType] = mapped_column(
        sa.Enum(RecommendationType, name="recommendation_type"), nullable=False
    )
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    status: Mapped[RecommendationStatus] = mapped_column(
        sa.Enum(RecommendationStatus, name="recommendation_status"),
        nullable=False,
        default=RecommendationStatus.ACTIVE,
        index=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    # SET NULL: recommendations outlive any single assessment record.
    source_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("assessments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (
        sa.Index("ix_recommendations_project_status", "project_id", "status"),
        sa.CheckConstraint("priority >= 0", name="ck_recommendation_priority"),
        # Deduplication guard: one row per lifecycle state per scope, so
        # repeated refreshes cannot duplicate ACTIVE recommendations.
        # Terminal rows never block regeneration (status is in the key).
        sa.UniqueConstraint(
            "user_id",
            "project_id",
            "concept_id",
            "type",
            "status",
            name="uq_recommendations_active_scope",
        ),
    )

    project: Mapped[Project] = relationship(back_populates="recommendations")
    user: Mapped[User] = relationship()
    concept: Mapped[Concept | None] = relationship()
    material: Mapped[Material | None] = relationship()
