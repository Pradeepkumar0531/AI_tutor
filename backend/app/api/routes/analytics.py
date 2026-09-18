"""Analytics endpoints: one aggregated dashboard read plus activity feeds.

Read-only by design (no POST/PUT/DELETE here). Every route verifies
authenticated user -> owned project; cross-tenant access returns 404 without
disclosure. Window clamps keep every query bounded.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_owned_project
from app.db.session import get_db
from app.models.enums import EventType
from app.models.learning import Project
from app.schemas.analytics import (
    ActivityDayRead,
    ActivityItemRead,
    DashboardSummaryRead,
    EventRead,
    MasteryTrendPointRead,
)
from app.schemas.common import Page
from app.services.analytics_service import AnalyticsService
from app.services.event_service import EventService

router = APIRouter(prefix="/projects", tags=["analytics"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]
RangeParam = Annotated[
    Literal["7d", "30d", "90d", "all"], Query(description="UTC window for activity data")
]


def _to_activity(item) -> ActivityItemRead:
    return ActivityItemRead(
        id=item.id,
        event_type=item.event_type,
        created_at=item.created_at,
        resource_id=item.resource_id,
        metadata=item.metadata,
        summary=item.summary,
    )


@router.get("/{project_id}/analytics/dashboard", response_model=DashboardSummaryRead)
def get_dashboard(project: OwnedProject, user: CurrentUser, session: SessionDep):
    service = AnalyticsService(session)
    summary = service.dashboard_summary(user_id=user.id, project_id=project.id)
    return DashboardSummaryRead(
        project_id=summary.project_id,
        project_name=summary.project_name,
        materials_count=summary.materials_count,
        materials_ready=summary.materials_ready,
        materials_failed=summary.materials_failed,
        documents_count=summary.documents_count,
        pages_count=summary.pages_count,
        chunks_count=summary.chunks_count,
        images_count=summary.images_count,
        concepts_count=summary.concepts_count,
        assessment_count=summary.assessment_count,
        questions_answered=summary.questions_answered,
        questions_correct=summary.questions_correct,
        questions_partial=summary.questions_partial,
        questions_incorrect=summary.questions_incorrect,
        average_assessment_score=summary.average_assessment_score,
        overall_mastery=summary.overall_mastery,
        mastery_confidence=summary.mastery_confidence,
        growth_status=summary.growth_status,
        active_recommendations=summary.active_recommendations,
        tutor_conversations=summary.tutor_conversations,
        tutor_messages=summary.tutor_messages,
        last_activity_at=summary.last_activity_at,
        has_learning_evidence=summary.has_learning_evidence,
    )


@router.get("/{project_id}/analytics/activity", response_model=Page[ActivityItemRead])
def get_activity(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    range: RangeParam = "30d",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    event_type: Annotated[list[EventType] | None, Query()] = None,
):
    service = AnalyticsService(session)
    items = service.activity(
        user_id=user.id,
        project_id=project.id,
        event_types=event_type,
        window=range,
        limit=limit,
    )
    return Page[ActivityItemRead](
        items=[_to_activity(item) for item in items],
        total=len(items),
        page=1,
        page_size=limit,
    )


@router.get("/{project_id}/analytics/activity-by-day", response_model=list[ActivityDayRead])
def get_activity_by_day(
    project: OwnedProject, user: CurrentUser, session: SessionDep, range: RangeParam = "30d"
):
    service = AnalyticsService(session)
    days = service.activity_by_day(user_id=user.id, project_id=project.id, window=range)
    return [ActivityDayRead(date=day.date, count=day.count) for day in days]


@router.get("/{project_id}/analytics/mastery-trend", response_model=list[MasteryTrendPointRead])
def get_mastery_trend(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    service = AnalyticsService(session)
    points = service.mastery_trend(user_id=user.id, project_id=project.id, limit=limit)
    return [
        MasteryTrendPointRead(date=p.date, score=p.score, assessment_id=p.assessment_id)
        for p in points
    ]


@router.get("/{project_id}/events", response_model=Page[EventRead])
def list_events(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    event_type: Annotated[list[EventType] | None, Query()] = None,
    since: Annotated[datetime | None, Query(description="UTC lower bound (inclusive)")] = None,
    until: Annotated[datetime | None, Query(description="UTC upper bound (inclusive)")] = None,
):
    """Project activity feed (tenant-scoped, newest first, offset pages)."""
    service = EventService(session)
    rows, total = service.feed(
        user_id=user.id,
        project_id=project.id,
        event_types=event_type,
        since=since,
        until=until,
        page=page,
        page_size=page_size,
    )
    from app.services.event_service import sanitize_payload

    return Page[EventRead](
        items=[
            EventRead(
                id=row.id,
                event_type=row.event_type,
                created_at=row.created_at,
                project_id=row.project_id,
                resource_id=row.entity_id,
                metadata=sanitize_payload(row.payload),
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
