"""Knowledge layer: project-scoped Concepts + typed ConceptRelationships.

Concepts are scoped per project (``uq_concepts_project_normalized``) — two projects
may share a name. Cross-project relationships are impossible at the database level:
both endpoints join through composite foreign keys on ``(project_id, concept_id)``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import ConceptRelationType, Difficulty
from app.models.mixins import CreatedMixin, FlexibleJSON, TimestampMixin

if TYPE_CHECKING:
    from app.models.learning import Project


class Concept(Base, TimestampMixin):
    __tablename__ = "concepts"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    difficulty: Mapped[Difficulty | None] = mapped_column(
        sa.Enum(Difficulty, name="difficulty"), nullable=True
    )
    concept_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", FlexibleJSON, nullable=True
    )

    __table_args__ = (
        # Enables composite FKs from concept_relationships so both endpoints are
        # provably in the same project; also speeds project+concept lookups.
        sa.UniqueConstraint("project_id", "id", name="uq_concepts_project_id"),
        sa.UniqueConstraint("project_id", "normalized_name", name="uq_concepts_project_normalized"),
    )

    project: Mapped[Project] = relationship(back_populates="concepts")

    @staticmethod
    def normalize_name(raw: str) -> str:
        return " ".join(raw.strip().lower().split())


class ConceptRelationship(Base, CreatedMixin):
    __tablename__ = "concept_relationships"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_concept_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    target_concept_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, nullable=False)
    relationship_type: Mapped[ConceptRelationType] = mapped_column(
        sa.Enum(ConceptRelationType, name="concept_relation_type"),
        nullable=False,
        default=ConceptRelationType.RELATED,
    )
    weight: Mapped[float] = mapped_column(sa.Float, nullable=False, default=1.0)

    __table_args__ = (
        sa.ForeignKeyConstraint(
            ["project_id", "source_concept_id"],
            ["concepts.project_id", "concepts.id"],
            ondelete="CASCADE",
            name="fk_rel_source_in_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "target_concept_id"],
            ["concepts.project_id", "concepts.id"],
            ondelete="CASCADE",
            name="fk_rel_target_in_project",
        ),
        sa.UniqueConstraint(
            "source_concept_id",
            "target_concept_id",
            "relationship_type",
            name="uq_rel_directional",
        ),
        sa.CheckConstraint("source_concept_id != target_concept_id", name="ck_rel_no_self_link"),
        sa.CheckConstraint("weight >= 0 AND weight <= 1", name="ck_rel_weight_bounds"),
    )

    source: Mapped[Concept] = relationship(foreign_keys=[source_concept_id])
    target: Mapped[Concept] = relationship(foreign_keys=[target_concept_id])
