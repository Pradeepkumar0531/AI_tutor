"""Knowledge (concepts + relationships) and tutor (conversations + messages)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa

from app.models.enums import ConceptRelationType, MessageRole
from app.models.knowledge import Concept, ConceptRelationship
from app.models.tutor import Conversation, Message
from app.repositories.base import BaseRepository


class ConceptRepository(BaseRepository[Concept]):
    model = Concept

    def get_or_create(
        self, *, project_id: uuid.UUID, name: str, description: str | None = None
    ) -> tuple[Concept, bool]:
        """Project-scoped get-or-create. Returns (concept, created)."""
        normalized = Concept.normalize_name(name)
        existing = self.session.scalar(
            sa.select(Concept).where(
                Concept.project_id == project_id,
                Concept.normalized_name == normalized,
            )
        )
        if existing is not None:
            return existing, False
        return (
            self.add(
                Concept(
                    project_id=project_id,
                    name=name.strip(),
                    normalized_name=normalized,
                    description=description,
                )
            ),
            True,
        )

    def get_many_for_project(
        self, concept_ids: list[uuid.UUID], project_id: uuid.UUID
    ) -> list[Concept]:
        """Batch-resolve concepts known to belong to a project (timeline names)."""
        if not concept_ids:
            return []
        return list(
            self.session.scalars(
                sa.select(Concept).where(
                    Concept.id.in_(concept_ids), Concept.project_id == project_id
                )
            )
        )

    def get_for_project(self, concept_id: uuid.UUID, project_id: uuid.UUID) -> Concept | None:
        return self.session.scalar(
            sa.select(Concept).where(Concept.id == concept_id, Concept.project_id == project_id)
        )

    def all_for_project(self, project_id: uuid.UUID) -> list[Concept]:
        """Unpaginated concept list for selection/generation (bounded by the
        caller's own clamps, never blindly consumed)."""
        return list(
            self.session.scalars(
                sa.select(Concept).where(Concept.project_id == project_id).order_by(Concept.name)
            )
        )

    def count_for_project(self, project_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(Concept.id)).where(Concept.project_id == project_id)
            )
            or 0
        )

    def list_for_project(
        self, project_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[Concept], int]:
        stmt = sa.select(Concept).where(Concept.project_id == project_id).order_by(Concept.name)
        return self.paginate(stmt, page=page, page_size=page_size)


class ConceptRelationshipRepository(BaseRepository[ConceptRelationship]):
    model = ConceptRelationship

    def link(
        self,
        *,
        project_id: uuid.UUID,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relationship_type: ConceptRelationType,
        weight: float = 1.0,
    ) -> ConceptRelationship:
        if source_id == target_id:
            raise ValueError("A concept cannot relate to itself")
        return self.add(
            ConceptRelationship(
                project_id=project_id,
                source_concept_id=source_id,
                target_concept_id=target_id,
                relationship_type=relationship_type,
                weight=weight,
            )
        )


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    def create(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, title: str = "New conversation"
    ) -> Conversation:
        return self.add(Conversation(project_id=project_id, user_id=user_id, title=title.strip()))

    def get_for_project(
        self, conversation_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation | None:
        return self.session.scalar(
            sa.select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.project_id == project_id,
                Conversation.user_id == user_id,
            )
        )

    def get_for_user(self, conversation_id: uuid.UUID, user_id: uuid.UUID) -> Conversation | None:
        """Ownership check without trusting any caller-supplied project id."""
        return self.session.scalar(
            sa.select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )

    def list_for_project(self, project_id: uuid.UUID, user_id: uuid.UUID) -> list[Conversation]:
        """Newest-first conversations for one owned project."""
        return list(
            self.session.scalars(
                sa.select(Conversation)
                .where(
                    Conversation.project_id == project_id,
                    Conversation.user_id == user_id,
                )
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            )
        )

    def count_for_project(self, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(Conversation.id)).where(
                    Conversation.project_id == project_id,
                    Conversation.user_id == user_id,
                )
            )
            or 0
        )


class MessageRepository(BaseRepository[Message]):
    model = Message

    def count_for_project(self, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
        """All messages across the user's project conversations (one join,
        no conversation bodies loaded)."""
        from app.models.tutor import Conversation

        return (
            self.session.scalar(
                sa.select(sa.func.count(Message.id))
                .select_from(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Conversation.project_id == project_id,
                    Conversation.user_id == user_id,
                )
            )
            or 0
        )

    def append(
        self,
        *,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
        model: str | None = None,
        provider: str | None = None,
        request_key: str | None = None,
    ) -> Message:
        return self.add(
            Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                model=model,
                provider=provider,
                request_key=request_key,
            )
        )

    def find_by_request_key(self, conversation_id: uuid.UUID, request_key: str) -> Message | None:
        """Idempotency lookup: a retried send resolves to the original message."""
        return self.session.scalar(
            sa.select(Message).where(
                Message.conversation_id == conversation_id,
                Message.request_key == request_key,
            )
        )

    def history(self, conversation_id: uuid.UUID, *, limit: int = 50) -> list[Message]:
        """Bounded history, newest last. Callers cap ``limit`` for prompt budgets."""
        limit = min(max(limit, 1), 200)
        rows = self.session.scalars(
            sa.select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        return sorted(rows, key=_message_sort_key)


def _message_sort_key(message: Message) -> tuple[datetime, str]:
    """Timezone-safe chronological key. SQLite returns naive datetimes while
    freshly-created rows still carry aware ones; normalize to aware UTC so
    mixed sessions never crash the comparison."""
    created = message.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (created, str(message.id))
