"""Learning-intelligence repositories: mastery, growth, recommendations, events."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa

from app.models.enums import (
    EventType,
    GrowthStatus,
    MasterySource,
    MasteryTrend,
    RecommendationStatus,
    RecommendationType,
)
from app.models.intelligence import Growth, Mastery, MasteryHistory, Recommendation
from app.models.mixins import utcnow
from app.models.ops import Event
from app.repositories.base import BaseRepository


class MasteryRepository(BaseRepository[Mastery]):
    model = Mastery

    def get_for_user(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_id: uuid.UUID
    ) -> Mastery | None:
        return self.session.scalar(
            sa.select(Mastery).where(
                Mastery.user_id == user_id,
                Mastery.project_id == project_id,
                Mastery.concept_id == concept_id,
            )
        )

    def record_observation(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        score: float,
        confidence: float = 0.0,
        source: MasterySource,
        trend: MasteryTrend = MasteryTrend.STABLE,
        assessment_id: uuid.UUID | None = None,
    ) -> tuple[Mastery, MasteryHistory]:
        """Upsert current mastery + append immutable history in one flush.

        No scoring algorithm here — the caller supplies the evaluated score.
        """
        mastery = self.get_for_user(user_id=user_id, project_id=project_id, concept_id=concept_id)
        if mastery is None:
            mastery = self.add(
                Mastery(user_id=user_id, project_id=project_id, concept_id=concept_id)
            )
        mastery.score = score
        mastery.confidence = confidence
        mastery.trend = trend
        mastery.last_assessed_at = utcnow()
        history = MasteryHistory(
            mastery=mastery,
            score=score,
            confidence=confidence,
            source=source,
            assessment_id=assessment_id,
        )
        self.session.add(history)
        return mastery, history

    def list_for_project(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        sort: str = "lowest",
    ) -> tuple[list[Mastery], int]:
        """Paginated mastery rows. ``sort`` in lowest (score asc) | recent
        (updated desc) | name (concept name). Unknown values fall back."""
        from app.models.knowledge import Concept

        stmt = sa.select(Mastery).where(
            Mastery.project_id == project_id, Mastery.user_id == user_id
        )
        if sort == "recent":
            stmt = stmt.order_by(Mastery.updated_at.desc(), Mastery.id.desc())
        elif sort == "name":
            stmt = stmt.join(Concept, Concept.id == Mastery.concept_id).order_by(
                Concept.name, Mastery.id
            )
        else:
            stmt = stmt.order_by(Mastery.score.asc(), Mastery.updated_at.desc())
        return self.paginate(stmt, page=page, page_size=page_size)

    def get_for_update(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, concept_id: uuid.UUID
    ) -> Mastery | None:
        """Row-locked read for concurrent completion safety. PostgreSQL takes
        a real row lock; other dialects compile it away harmlessly."""
        stmt = sa.select(Mastery).where(
            Mastery.user_id == user_id,
            Mastery.project_id == project_id,
            Mastery.concept_id == concept_id,
        )
        bind = self.session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        return self.session.scalar(stmt)

    def history_for_mastery(
        self, mastery_id: uuid.UUID, *, limit: int = 50
    ) -> list[MasteryHistory]:
        """Newest-last history window for trend/explanation. Bounded. Reversed
        in Python (never compared) so SQLite-naive and aware datetimes can't
        collide in a sort."""
        limit = min(max(limit, 1), 200)
        rows = list(
            self.session.scalars(
                sa.select(MasteryHistory)
                .where(MasteryHistory.mastery_id == mastery_id)
                .order_by(MasteryHistory.created_at.desc(), MasteryHistory.id.desc())
                .limit(limit)
            )
        )
        rows.reverse()
        return rows

    def history_count(self, mastery_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(MasteryHistory.id)).where(
                    MasteryHistory.mastery_id == mastery_id
                )
            )
            or 0
        )

    def history_exists(self, mastery_id: uuid.UUID, assessment_id: uuid.UUID) -> bool:
        return (
            self.session.scalar(
                sa.select(MasteryHistory.id).where(
                    MasteryHistory.mastery_id == mastery_id,
                    MasteryHistory.assessment_id == assessment_id,
                )
            )
            is not None
        )

    def history_counts(self, mastery_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Single-query observation counts per mastery (list-view evidence)."""
        if not mastery_ids:
            return {}
        rows = self.session.execute(
            sa.select(MasteryHistory.mastery_id, sa.func.count(MasteryHistory.id))
            .where(MasteryHistory.mastery_id.in_(mastery_ids))
            .group_by(MasteryHistory.mastery_id)
        ).all()
        return {mastery_id: total for mastery_id, total in rows}

    def latest_history(
        self, mastery_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, MasteryHistory]:
        """Newest observation per mastery in two bounded queries. Uses a
        portable ROW_NUMBER window (PostgreSQL + SQLite) so read paths never
        pay one round trip per concept."""
        if not mastery_ids:
            return {}
        rn = (
            sa.func.row_number()
            .over(
                partition_by=MasteryHistory.mastery_id,
                order_by=(MasteryHistory.created_at.desc(), MasteryHistory.id.desc()),
            )
            .label("rn")
        )
        sub = (
            sa.select(MasteryHistory.id.label("hid"), rn)
            .where(MasteryHistory.mastery_id.in_(mastery_ids))
            .subquery()
        )
        ids = list(self.session.scalars(sa.select(sub.c.hid).where(sub.c.rn == 1)))
        if not ids:
            return {}
        rows = self.session.scalars(
            sa.select(MasteryHistory).where(MasteryHistory.id.in_(ids))
        )
        return {row.mastery_id: row for row in rows}


class GrowthRepository(BaseRepository[Growth]):
    model = Growth

    def list_for_user_project(
        self, user_id: uuid.UUID, project_id: uuid.UUID, *, limit: int = 500
    ) -> list[Growth]:
        """All per-concept growth rows for aggregation. Bounded (concepts per
        project are few); the project aggregate itself is computed live."""
        return list(
            self.session.scalars(
                sa.select(Growth)
                .where(Growth.user_id == user_id, Growth.project_id == project_id)
                .order_by(Growth.concept_id)
                .limit(min(max(limit, 1), 1000))
            )
        )

    def refresh(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID,
        status: GrowthStatus,
        change_score: float | None = None,
        summary: str | None = None,
    ) -> Growth:
        existing = self.session.scalar(
            sa.select(Growth).where(
                Growth.user_id == user_id,
                Growth.project_id == project_id,
                Growth.concept_id == concept_id,
            )
        )
        if existing is None:
            return self.add(
                Growth(
                    user_id=user_id,
                    project_id=project_id,
                    concept_id=concept_id,
                    status=status,
                    change_score=change_score,
                    summary=summary,
                )
            )
        existing.status = status
        existing.change_score = change_score
        existing.summary = summary
        return existing


class RecommendationRepository(BaseRepository[Recommendation]):
    model = Recommendation

    def create(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        type: RecommendationType,
        title: str,
        concept_id: uuid.UUID | None = None,
        material_id: uuid.UUID | None = None,
        description: str | None = None,
        reason: str | None = None,
        priority: int = 0,
        source_assessment_id: uuid.UUID | None = None,
    ) -> Recommendation:
        return self.add(
            Recommendation(
                project_id=project_id,
                user_id=user_id,
                type=type,
                title=title.strip(),
                concept_id=concept_id,
                material_id=material_id,
                description=description,
                reason=reason,
                priority=priority,
                source_assessment_id=source_assessment_id,
            )
        )

    def find_active_scope(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        concept_id: uuid.UUID | None,
        type: RecommendationType,
    ) -> Recommendation | None:
        """Dedup lookup: the ACTIVE row for one scope, if any."""
        stmt = sa.select(Recommendation).where(
            Recommendation.user_id == user_id,
            Recommendation.project_id == project_id,
            Recommendation.type == type,
            Recommendation.status == RecommendationStatus.ACTIVE,
        )
        if concept_id is None:
            stmt = stmt.where(Recommendation.concept_id.is_(None))
        else:
            stmt = stmt.where(Recommendation.concept_id == concept_id)
        return self.session.scalar(stmt)

    def set_status(
        self, recommendation: Recommendation, status: RecommendationStatus
    ) -> Recommendation:
        """Lifecycle transition with terminal timestamps."""
        from app.models.mixins import utcnow

        recommendation.status = status
        if status == RecommendationStatus.COMPLETED:
            recommendation.completed_at = recommendation.completed_at or utcnow()
        return recommendation

    def counts_by_status(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[RecommendationStatus, int]:
        """Single GROUP BY for the dashboard recommendation breakdown."""
        rows = self.session.execute(
            sa.select(Recommendation.status, sa.func.count(Recommendation.id))
            .where(
                Recommendation.project_id == project_id,
                Recommendation.user_id == user_id,
            )
            .group_by(Recommendation.status)
        ).all()
        return {status: total for status, total in rows}

    def get_many_for_project(
        self, recommendation_ids: list[uuid.UUID], project_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Recommendation]:
        """Batch-resolve owned recommendations (timeline titles)."""
        if not recommendation_ids:
            return []
        return list(
            self.session.scalars(
                sa.select(Recommendation).where(
                    Recommendation.id.in_(recommendation_ids),
                    Recommendation.project_id == project_id,
                    Recommendation.user_id == user_id,
                )
            )
        )

    def get_for_project(
        self, recommendation_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> Recommendation | None:
        return self.session.scalar(
            sa.select(Recommendation).where(
                Recommendation.id == recommendation_id,
                Recommendation.project_id == project_id,
                Recommendation.user_id == user_id,
            )
        )

    def list_active(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Recommendation], int]:
        stmt = (
            sa.select(Recommendation)
            .where(
                Recommendation.project_id == project_id,
                Recommendation.user_id == user_id,
                Recommendation.status == RecommendationStatus.ACTIVE,
            )
            .order_by(Recommendation.priority.desc(), Recommendation.created_at.desc())
        )
        return self.paginate(stmt, page=page, page_size=page_size)


class EventRepository(BaseRepository[Event]):
    model = Event

    def append(
        self,
        *,
        event_type: EventType,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        return self.add(
            Event(
                event_type=event_type,
                user_id=user_id,
                project_id=project_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
            )
        )

    def list_for_project(
        self, project_id: uuid.UUID, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[Event], int]:
        stmt = (
            sa.select(Event).where(Event.project_id == project_id).order_by(Event.created_at.desc())
        )
        return self.paginate(stmt, page=page, page_size=page_size)

    def feed(
        self,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        event_types: list[EventType] | None = None,
        since=None,
        until=None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Event], int]:
        """Tenant-scoped activity feed: project + user predicates live in SQL
        (never fetch-then-filter), newest first, optional type/date filters."""
        stmt = sa.select(Event).where(Event.project_id == project_id, Event.user_id == user_id)
        if event_types:
            stmt = stmt.where(Event.event_type.in_(event_types))
        if since is not None:
            stmt = stmt.where(Event.created_at >= since)
        if until is not None:
            stmt = stmt.where(Event.created_at <= until)
        stmt = stmt.order_by(Event.created_at.desc(), Event.id.desc())
        return self.paginate(stmt, page=page, page_size=page_size)

    def count_by_day(
        self, project_id: uuid.UUID, user_id: uuid.UUID, *, since=None
    ) -> list[tuple[object, int]]:
        """(day, count) grouped by stored UTC calendar date on both dialects.
        Callers normalize the day label; bounded by ``since``."""
        day = sa.func.date(Event.created_at).label("day")
        stmt = (
            sa.select(day, sa.func.count(Event.id))
            .where(Event.project_id == project_id, Event.user_id == user_id)
            .group_by(day)
            .order_by(day)
        )
        if since is not None:
            stmt = stmt.where(Event.created_at >= since)
        return [(day, int(total)) for day, total in self.session.execute(stmt).all()]
