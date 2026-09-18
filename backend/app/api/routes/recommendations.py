"""Recommendation endpoints: active list, detail, complete, dismiss.

Generation happens server-side on assessment completion
(RecommendationService.refresh_after_assessment); the browser only reads and
transitions lifecycle state. All routes enforce user -> project ->
recommendation ownership with 404 isolation.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_owned_project
from app.db.session import get_db
from app.models.learning import Project
from app.schemas.common import Page
from app.schemas.growth import RecommendationRead
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/projects", tags=["recommendations"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]


def _to_read(item: dict) -> RecommendationRead:
    row = item["row"]
    return RecommendationRead(
        id=row.id,
        project_id=row.project_id,
        concept_id=row.concept_id,
        concept_name=item["concept_name"],
        material_id=row.material_id,
        material_name=item["material_name"],
        type=row.type,
        title=row.title,
        description=row.description,
        reason=row.reason,
        actions=item["actions"],
        priority=row.priority,
        status=row.status,
        source_assessment_id=row.source_assessment_id,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


@router.get("/{project_id}/recommendations", response_model=Page[RecommendationRead])
def list_recommendations(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    service = RecommendationService(session)
    rows, total = service.list_active(
        user_id=user.id, project_id=project.id, page=page, page_size=page_size
    )
    described = service.describe_many(user_id=user.id, project_id=project.id, rows=rows)
    return Page[RecommendationRead](
        items=[_to_read(item) for item in described],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}/recommendations/{recommendation_id}", response_model=RecommendationRead)
def get_recommendation(
    recommendation_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
):
    service = RecommendationService(session)
    row = service.get(user_id=user.id, project_id=project.id, recommendation_id=recommendation_id)
    return _to_read(service.describe(user_id=user.id, project_id=project.id, row=row))


@router.post(
    "/{project_id}/recommendations/{recommendation_id}/complete",
    response_model=RecommendationRead,
)
def complete_recommendation(
    recommendation_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
):
    service = RecommendationService(session)
    row = service.complete(
        user_id=user.id, project_id=project.id, recommendation_id=recommendation_id
    )
    return _to_read(service.describe(user_id=user.id, project_id=project.id, row=row))


@router.post(
    "/{project_id}/recommendations/{recommendation_id}/dismiss",
    response_model=RecommendationRead,
)
def dismiss_recommendation(
    recommendation_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
):
    service = RecommendationService(session)
    row = service.dismiss(
        user_id=user.id, project_id=project.id, recommendation_id=recommendation_id
    )
    return _to_read(service.describe(user_id=user.id, project_id=project.id, row=row))
