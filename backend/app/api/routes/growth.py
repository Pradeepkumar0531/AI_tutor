"""Growth endpoints: project aggregate, per-concept distribution, history.

The aggregate is computed live from persisted Mastery rows on every read
(never stale, nothing extra to migrate); per-concept Growth rows are the
persisted trail refreshed on assessment completion. Cold-start projects
return STABLE with has_evidence=False — never failure.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_owned_project
from app.db.session import get_db
from app.models.learning import Project
from app.schemas.common import Page
from app.schemas.growth import ConceptGrowthRead, GrowthHistoryPointRead, GrowthRead
from app.services.growth_service import GrowthService

router = APIRouter(prefix="/projects", tags=["growth"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]


@router.get("/{project_id}/growth", response_model=GrowthRead)
def get_growth(project: OwnedProject, user: CurrentUser, session: SessionDep):
    service = GrowthService(session)
    aggregate = service.project_growth(user_id=user.id, project_id=project.id)
    concepts = service.concept_growth(user_id=user.id, project_id=project.id)
    return GrowthRead(
        project_id=project.id,
        status=aggregate.status,
        has_evidence=aggregate.has_evidence,
        overall_mastery=aggregate.overall_mastery,
        average_confidence=aggregate.average_confidence,
        concepts_improving=aggregate.concepts_improving,
        concepts_stable=aggregate.concepts_stable,
        concepts_requiring_attention=aggregate.concepts_requiring_attention,
        assessed_concepts=aggregate.assessed_concepts,
        assessment_count=aggregate.assessment_count,
        questions_answered=aggregate.questions_answered,
        updated_at=aggregate.updated_at,
        concepts=[
            ConceptGrowthRead(
                concept_id=c.concept_id,
                concept_name=c.concept_name,
                status=c.status,
                mastery_score=c.mastery_score,
                confidence=c.confidence,
                trend=c.trend,
                change_score=c.change_score,
                summary=c.summary,
            )
            for c in concepts
        ],
    )


@router.get("/{project_id}/growth/history", response_model=Page[GrowthHistoryPointRead])
def get_growth_history(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
):
    service = GrowthService(session)
    points = service.history(user_id=user.id, project_id=project.id, limit=limit)
    return Page[GrowthHistoryPointRead](
        items=[
            GrowthHistoryPointRead(date=p.date, score=p.score, assessment_id=p.assessment_id)
            for p in points
        ],
        total=len(points),
        page=1,
        page_size=limit,
    )
