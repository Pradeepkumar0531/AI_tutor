"""Tutor persistence: Conversation (per project+user) -> Message (immutable log).

Messages store light observability metadata (model/provider/latency/token usage)
but never retrieval context dumps or secrets.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import MessageRole
from app.models.mixins import CreatedMixin, FlexibleJSON, TimestampMixin

if TYPE_CHECKING:
    from app.models.learning import Project
    from app.models.users import User


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(sa.String(200), nullable=False, default="New conversation")

    __table_args__ = (sa.Index("ix_conversations_project_user", "project_id", "user_id"),)

    project: Mapped[Project] = relationship(back_populates="conversations")
    user: Mapped[User] = relationship()
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )


class Message(Base, CreatedMixin):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[MessageRole] = mapped_column(
        sa.Enum(MessageRole, name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    provider: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(FlexibleJSON, nullable=True)
    retrieval_count: Mapped[int | None] = mapped_column(sa.Integer, nullable=True, default=0)
    request_key: Mapped[str | None] = mapped_column(sa.String(64), nullable=True, unique=True)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(FlexibleJSON, nullable=True)
    tutor_metadata: Mapped[dict[str, Any] | None] = mapped_column(FlexibleJSON, nullable=True)

    __table_args__ = (
        sa.Index("ix_messages_conversation_created", "conversation_id", "created_at"),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="ck_messages_latency"),
        sa.CheckConstraint(
            "retrieval_count IS NULL OR retrieval_count >= 0", name="ck_messages_retrieval"
        ),
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
