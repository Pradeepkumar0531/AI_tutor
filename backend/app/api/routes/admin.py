"""Admin endpoints: platform operations for administrators only.

Every route depends on ``require_admin`` (server-side; frontend hiding is
cosmetic). Learners get 403, unauthenticated callers 401. Responses are
secret-free aggregates and paginated lists — never full-table loads.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.auth.dependencies import AdminUser, SessionDep
from app.core.exceptions import NotFoundError
from app.schemas.admin import (
    AdminAiSummaryItemRead,
    AdminAiUsageRead,
    AdminAssessmentRead,
    AdminEvaluationRunRead,
    AdminEvaluationSummaryRead,
    AdminEventRead,
    AdminHealthRead,
    AdminJobRead,
    AdminOverviewRead,
    AdminRagDiagnoseRead,
    AdminRagResultRead,
    AdminRecommendationRead,
    AdminSpaceRead,
    AdminUserJourneyRead,
    AdminUserRead,
)
from app.schemas.common import Page
from app.services.admin_service import AdminService
from app.services.ai_usage_service import AiUsageService

router = APIRouter(prefix="/admin", tags=["admin"])

Admin = AdminUser
SessionD = SessionDep


def _page(items: list, total: int, limit: int, offset: int) -> Page:
    return Page(items=items, total=total, page=offset // limit + 1, page_size=limit)


@router.get("/overview", response_model=AdminOverviewRead)
def overview(admin: Admin, session: SessionD):
    return AdminOverviewRead(**AdminService(session).overview())


@router.get("/users", response_model=Page[AdminUserRead])
def list_users(
    admin: Admin,
    session: SessionD,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=120)] = None,
):
    rows, total = AdminService(session).list_users(limit=limit, offset=offset, search=search)
    return _page(
        [
            AdminUserRead(
                id=u.id,
                email=u.email,
                display_name=u.display_name,
                role=u.role,
                is_active=u.is_active,
                last_login_at=u.last_login_at,
                created_at=u.created_at,
            )
            for u in rows
        ],
        total,
        limit,
        offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserJourneyRead)
def inspect_user(user_id: uuid.UUID, admin: Admin, session: SessionD):
    journey = AdminService(session).user_journey(user_id)
    if journey is None:
        raise NotFoundError("User not found.")
    u = journey["user"]
    return AdminUserJourneyRead(
        user=AdminUserRead(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            is_active=u.is_active,
            last_login_at=u.last_login_at,
            created_at=u.created_at,
        ),
        project_ids=journey["project_ids"],
        spaces=[AdminSpaceRead(id=s.id, name=s.name) for s in journey["spaces"]],
        assessments=[
            AdminAssessmentRead(
                id=a.id,
                project_id=a.project_id,
                status=str(a.status),
                score=a.score,
                created_at=a.created_at,
            )
            for a in journey["assessments"]
        ],
        recommendations=[
            AdminRecommendationRead(
                id=r.id,
                project_id=r.project_id,
                type=str(r.type),
                title=r.title,
                status=str(r.status),
            )
            for r in journey["recommendations"]
        ],
        mastery_concepts=journey["mastery_concepts"],
        mastery_avg=journey["mastery_avg"],
        ai_requests=journey["ai_requests"],
        ai_estimated_cost_usd=journey["ai_estimated_cost_usd"],
        recent_events=[
            AdminEventRead(
                id=e.id,
                event_type=str(e.event_type),
                user_id=e.user_id,
                project_id=e.project_id,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                created_at=e.created_at,
            )
            for e in journey["recent_events"]
        ],
    )


@router.get("/activity", response_model=Page[AdminEventRead])
def activity(
    admin: Admin,
    session: SessionD,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    user_id: uuid.UUID | None = None,
    space_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    event_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
):
    rows, total = AdminService(session).activity(
        limit=limit,
        offset=offset,
        user_id=user_id,
        space_id=space_id,
        project_id=project_id,
        event_type=event_type,
        since=since,
        until=until,
    )
    return _page(
        [
            AdminEventRead(
                id=e.id,
                event_type=str(e.event_type),
                user_id=e.user_id,
                project_id=e.project_id,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                created_at=e.created_at,
            )
            for e in rows
        ],
        total,
        limit,
        offset,
    )


@router.get("/jobs", response_model=Page[AdminJobRead])
def jobs(
    admin: Admin,
    session: SessionD,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    status: str | None = None,
):
    rows, total = AdminService(session).jobs(limit=limit, offset=offset, status=status)
    return _page(
        [
            AdminJobRead(
                id=j.id,
                job_type=j.job_type,
                status=str(j.status),
                attempt_count=j.attempt_count,
                max_retries=j.max_retries,
                material_id=j.material_id,
                project_id=j.project_id,
                error_summary=(j.error[:300] if j.error else None),
                created_at=j.created_at,
                started_at=j.started_at,
                completed_at=j.completed_at,
            )
            for j in rows
        ],
        total,
        limit,
        offset,
    )


@router.get("/health", response_model=AdminHealthRead)
def health(admin: Admin, session: SessionD):
    return AdminHealthRead(**AdminService(session).health())


@router.get("/ai-usage/summary", response_model=list[AdminAiSummaryItemRead])
def ai_usage_summary(
    admin: Admin,
    session: SessionD,
    user_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return [
        AdminAiSummaryItemRead(**row)
        for row in AiUsageService(session).summary(user_id=user_id, limit=limit)
    ]


@router.get("/ai-usage", response_model=Page[AdminAiUsageRead])
def ai_usage(
    admin: Admin,
    session: SessionD,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    user_id: uuid.UUID | None = None,
    feature: str | None = None,
):
    svc = AiUsageService(session)
    rows = svc.recent(limit=limit, user_id=user_id, feature=feature)
    total = svc.count(user_id=user_id, feature=feature)
    return _page([AdminAiUsageRead(**svc.to_dict(r)) for r in rows], total, limit, offset)


@router.get("/evaluations/summary", response_model=AdminEvaluationSummaryRead | None)
def evaluations_summary(admin: Admin, session: SessionD):
    summary = AdminService(session).evaluation_summary()
    return AdminEvaluationSummaryRead(**summary) if summary else None


@router.post("/evaluations/run", response_model=AdminEvaluationRunRead)
def run_evaluations(admin: Admin, session: SessionD):
    """Execute the curated evaluation suite (deterministic test doubles,
    sandboxed + rolled back) and persist the run. Bounded and synchronous:
    16 small cases, no browser, no live providers, no cost."""
    import asyncio

    from app.evaluation.runner import persist_run, run_all

    results = asyncio.run(run_all(session))
    session.rollback()  # sandbox rows never persist; only outcomes below do
    run = persist_run(session, triggered_by_id=admin.id, results=results)
    return AdminEvaluationRunRead(
        id=run.id,
        triggered_by_id=run.triggered_by_id,
        total_cases=run.total_cases,
        passed=run.passed,
        failed=run.failed,
        created_at=run.created_at,
    )


@router.get("/evaluations", response_model=Page[AdminEvaluationRunRead])
def evaluations(
    admin: Admin,
    session: SessionD,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    rows, total = AdminService(session).evaluation_runs(limit=limit, offset=offset)
    return _page(
        [
            AdminEvaluationRunRead(
                id=r.id,
                triggered_by_id=r.triggered_by_id,
                total_cases=r.total_cases,
                passed=r.passed,
                failed=r.failed,
                created_at=r.created_at,
            )
            for r in rows
        ],
        total,
        limit,
        offset,
    )


@router.get("/rag/diagnose", response_model=AdminRagDiagnoseRead)
async def rag_diagnose(
    admin: Admin,
    session: SessionD,
    project_id: Annotated[uuid.UUID, Query()],
    query: Annotated[str, Query(min_length=1, max_length=1000)],
    top_k: Annotated[int, Query(ge=1, le=20)] = 10,
):
    """Admin-only RAG diagnostic: run retrieval for a query against any
    project and return scores + provenance previews. Embeddings are never
    exposed; only the configured model name and dimension are reported."""
    from app.ai.service import ai_service
    from app.core.config import get_settings
    from app.rag.retrieval import RetrievalService

    settings = get_settings()
    service = RetrievalService(session, ai_service.embedding_service(settings), settings)
    result = await service.diagnose_for_admin(project_id=project_id, query=query, top_k=top_k)
    return AdminRagDiagnoseRead(
        query=result.query,
        project_id=project_id,
        embedding_model=settings.google_embedding_model,
        embedding_dimension=settings.embedding_dimensions,
        top_k=top_k,
        threshold=settings.rag_similarity_threshold,
        retrieval_count=len(result.results),
        best_similarity=result.best_similarity,
        insufficient_evidence=result.insufficient_evidence,
        results=[
            AdminRagResultRead(
                chunk_id=r.chunk_id,
                document_id=r.document_id,
                material_id=r.material_id,
                material_name=r.material_name,
                page_start=r.page_start,
                page_end=r.page_end,
                similarity=r.similarity,
                text_preview=r.text[:300],
            )
            for r in result.results
        ],
    )
