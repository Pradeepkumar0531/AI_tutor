"""Persisted AI usage: one row per provider call that services record.

Complements log lines (ephemeral) with queryable history for the Admin
Dashboard. NEVER stores prompts, answers, keys, or document content — only
operational metadata. Token counts are recorded only when the provider
actually reports them; cost is a rough static estimate (see AiUsageService).
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedMixin


class AiUsage(Base, CreatedMixin):
    __tablename__ = "ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    feature: Mapped[str] = mapped_column(sa.String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    model: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    latency_ms: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    input_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    success: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    error_type: Mapped[str | None] = mapped_column(sa.String(128), nullable=True)
    request_id: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)

    __table_args__ = (
        sa.Index("ix_ai_usage_user_created", "user_id", "created_at"),
        sa.Index("ix_ai_usage_project_created", "project_id", "created_at"),
    )
