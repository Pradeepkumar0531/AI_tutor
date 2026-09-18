"""Knowledge endpoints: status, concepts, project-scoped RAG search.

Every route verifies authenticated user -> owned project. Retrieval filters by
project inside the database query; embeddings and storage keys never appear in
responses; business logic lives in services.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_owned_project
from app.db.session import get_db
from app.jobs.dispatch import dispatch_knowledge
from app.models.learning import Project
from app.schemas.common import Page
from app.schemas.knowledge import (
    CitationRead,
    ConceptDetailRead,
    ConceptMaterialLink,
    KnowledgeStatusRead,
    KnowledgeTotals,
    ReprocessKnowledgeResponse,
    RetrievedChunkRead,
    SearchRequest,
    SearchResponse,
)
from app.schemas.materials import ConceptRead
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/projects", tags=["knowledge"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]


@router.get("/{project_id}/knowledge", response_model=KnowledgeStatusRead)
def get_knowledge_status(
    project: OwnedProject, user: CurrentUser, session: SessionDep
) -> KnowledgeStatusRead:
    status = KnowledgeService(session).get_status(user_id=user.id, project_id=project.id)
    return KnowledgeStatusRead(
        project_id=project.id,
        status=status.status,
        totals=KnowledgeTotals(
            chunks_total=status.chunks_total,
            chunks_embedded=status.chunks_embedded,
            concepts=status.concepts,
            materials_ready=status.materials_ready,
        ),
    )


@router.get("/{project_id}/concepts", response_model=Page[ConceptRead])
def list_concepts(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ConceptRead]:
    items, total = KnowledgeService(session).list_concepts(
        user_id=user.id, project_id=project.id, page=page, page_size=page_size
    )
    return Page[ConceptRead](
        items=[ConceptRead.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}/concepts/{concept_id}", response_model=ConceptDetailRead)
def get_concept(
    concept_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> ConceptDetailRead:
    concept, materials, chunk_count, pages = KnowledgeService(session).get_concept_detail(
        user_id=user.id, project_id=project.id, concept_id=concept_id
    )
    detail = ConceptDetailRead.model_validate(concept)
    detail.materials = [ConceptMaterialLink(**m) for m in materials]
    detail.chunk_count = chunk_count
    detail.pages = pages
    return detail


@router.post("/{project_id}/knowledge/search", response_model=SearchResponse)
async def search_knowledge(
    body: SearchRequest,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> SearchResponse:
    material_ids = list(dict.fromkeys(body.material_ids or []))
    result = await KnowledgeService(session).search(
        user_id=user.id,
        project_id=project.id,
        query=body.query,
        top_k=body.top_k,
        threshold=body.threshold,
        material_ids=material_ids or None,
    )
    return SearchResponse(
        query=result["query"],
        results=[RetrievedChunkRead(**r) for r in result["results"]],
        citations=[
            CitationRead(
                **c,
                label=_citation_label(c["material_name"], c["page_start"], c["page_end"]),
            )
            for c in result["citations"]
        ],
        context=result["context"],
        insufficient_evidence=result["insufficient_evidence"],
    )


def _citation_label(material_name: str, page_start: int | None, page_end: int | None) -> str:
    if page_start is None and page_end is None:
        return f"{material_name} — page unknown"
    if page_end is None or page_end == page_start:
        return f"{material_name} — Page {page_start}"
    return f"{material_name} — Pages {page_start}–{page_end}"


@router.post(
    "/{project_id}/materials/{material_id}/reprocess-knowledge",
    response_model=ReprocessKnowledgeResponse,
    status_code=202,
)
def reprocess_knowledge(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> ReprocessKnowledgeResponse:
    result = KnowledgeService(session).reprocess_material_knowledge(
        user_id=user.id, project_id=project.id, material_id=material_id
    )
    dispatch_knowledge(material_id)
    return ReprocessKnowledgeResponse(
        material_id=result["material_id"],
        job_status=result["job_status"],
        reset=result["reset"],
    )
