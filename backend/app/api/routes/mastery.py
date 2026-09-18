"""Mastery endpoints: per-concept estimates, detail explanations, history.

Every route verifies authenticated user -> owned project -> in-project
concept. Cross-tenant access returns 404 without disclosure. All numbers are
computed server-side by MasteryService (deterministic, no LLM); there is no
endpoint that writes mastery directly — estimates only move through
assessment completion.
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
from app.schemas.mastery import MasteryDetailRead, MasteryHistoryRead, MasteryRead
from app.services.mastery_service import MasteryService

router = APIRouter(prefix="/projects", tags=["mastery"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]


def _to_read(item: dict) -> MasteryRead:
    mastery = item["mastery"]
    return MasteryRead(
        concept_id=mastery.concept_id,
        concept_name=item["concept_name"],
        mastery_score=round(min(max(mastery.score / 100, 0.0), 1.0), 4),
        confidence=round(min(max(mastery.confidence, 0.0), 1.0), 4),
        trend=mastery.trend,
        evidence_count=item["evidence_count"],
        recent_performance=[],
        has_evidence=True,
        updated_at=mastery.updated_at,
    )


@router.get("/{project_id}/mastery", response_model=Page[MasteryRead])
def list_mastery(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Annotated[str, Query(pattern="^(lowest|recent|name)$")] = "lowest",
):
    service = MasteryService(session)
    items, total = service.list_mastery(
        user_id=user.id, project_id=project.id, page=page, page_size=page_size, sort=sort
    )
    return Page[MasteryRead](
        items=[_to_read(item) for item in items], total=total, page=page, page_size=page_size
    )


@router.get("/{project_id}/mastery/{concept_id}", response_model=MasteryDetailRead)
def get_mastery(
    concept_id: uuid.UUID, project: OwnedProject, user: CurrentUser, session: SessionDep
):
    service = MasteryService(session)
    explanation = service.explain(user_id=user.id, project_id=project.id, concept_id=concept_id)
    return MasteryDetailRead(
        concept_id=explanation.concept_id,
        concept_name=explanation.concept_name,
        mastery_score=explanation.mastery_score,
        confidence=explanation.confidence,
        trend=explanation.trend,
        evidence_count=explanation.evidence_assessments,
        recent_performance=list(explanation.recent_performance),
        has_evidence=explanation.has_evidence,
        updated_at=explanation.updated_at,
        evidence_questions=explanation.evidence_questions,
        contributing_assessments=list(explanation.contributing_assessments),
    )


@router.get(
    "/{project_id}/mastery/{concept_id}/history",
    response_model=Page[MasteryHistoryRead],
)
def get_mastery_history(
    concept_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    service = MasteryService(session)
    rows, total = service.mastery_history(
        user_id=user.id,
        project_id=project.id,
        concept_id=concept_id,
        page=page,
        page_size=page_size,
    )
    return Page[MasteryHistoryRead](
        items=[
            MasteryHistoryRead(
                id=row.id,
                assessment_id=row.assessment_id,
                previous_score=(
                    round(row.previous_score / 100, 4) if row.previous_score is not None else None
                ),
                new_score=round(min(max(row.score / 100, 0.0), 1.0), 4),
                confidence=round(min(max(row.confidence, 0.0), 1.0), 4),
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
