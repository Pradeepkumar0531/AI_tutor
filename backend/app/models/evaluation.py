"""Curated AI evaluation runs: machine-readable results for the Admin Dashboard.

Cases themselves live in code (``app/evaluation/cases.py``) so they are
reviewable and versioned; only *outcomes* persist here. No learner content,
prompts, or secrets are stored — just pass/fail, scores, and short reasons.
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import CreatedMixin


class EvaluationRun(Base, CreatedMixin):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    total_cases: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

    results: Mapped[list[EvaluationResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class EvaluationResult(Base, CreatedMixin):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(sa.String(32), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    passed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    score: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    expected: Mapped[str] = mapped_column(sa.String(512), nullable=False, default="")
    actual: Mapped[str] = mapped_column(sa.String(512), nullable=False, default="")

    run: Mapped[EvaluationRun] = relationship(back_populates="results")
