"""Material endpoints: upload, status, document inspection, reprocess, archive.

Every route verifies authenticated user -> owned project -> project material.
Upload persists the object + rows transactionally and enqueues Celery *after*
commit; the worker does all extraction off-request.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, get_owned_project
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.jobs.dispatch import dispatch_processing
from app.models.enums import MaterialStatus
from app.models.learning import Project
from app.schemas.common import Page
from app.schemas.knowledge import MaterialKnowledgeSummary
from app.schemas.materials import (
    ChunkRead,
    DocumentDetailRead,
    DocumentImageRead,
    MaterialDetailRead,
    MaterialRead,
)
from app.services.knowledge_service import KnowledgeService
from app.services.material_service import MaterialService

router = APIRouter(prefix="/projects", tags=["materials"])

SessionDep = Annotated[Session, Depends(get_db)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]

MAX_FORM_TITLE = 200


@router.post("/{project_id}/materials", response_model=MaterialRead, status_code=201)
async def upload_material(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="PDF document")],
    title: Annotated[str | None, Form(max_length=MAX_FORM_TITLE)] = None,
) -> MaterialRead:
    data = await file.read()
    material = MaterialService(session).upload_material(
        user_id=user.id,
        project_id=project.id,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
        title=title,
    )
    # Post-commit: the worker must never race uncommitted rows. Broker outages
    # leave the job QUEUED (picked up later); the upload still returns 201.
    dispatch_processing(material.id)
    return MaterialRead.model_validate(material)


@router.get("/{project_id}/materials", response_model=Page[MaterialRead])
def list_materials(
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[MaterialStatus | None, Query()] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> Page[MaterialRead]:
    svc = MaterialService(session)
    items, total, page_counts, chunk_counts = svc.list_materials(
        user_id=user.id,
        project_id=project.id,
        page=page,
        page_size=page_size,
        status=status,
        include_archived=include_archived,
    )
    return Page[MaterialRead](
        items=[
            MaterialRead.model_validate(m).model_copy(
                update={
                    "page_count": page_counts.get(m.id),
                    "chunk_count": chunk_counts.get(m.id, 0),
                }
            )
            for m in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}/materials/{material_id}", response_model=MaterialDetailRead)
def get_material(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> MaterialDetailRead:
    material, document, chunk_count, image_count = MaterialService(session).get_material_detail(
        user_id=user.id, project_id=project.id, material_id=material_id
    )
    detail = MaterialDetailRead.model_validate(material)
    detail.chunk_count = chunk_count
    detail.image_count = image_count
    if document is not None:
        doc_read = DocumentDetailRead.model_validate(document)
        doc_read.chunk_count = chunk_count
        doc_read.image_count = image_count
        detail.document = doc_read
    knowledge = KnowledgeService(session).material_knowledge(
        user_id=user.id, project_id=project.id, material_id=material.id
    )
    detail.knowledge = MaterialKnowledgeSummary(**knowledge)
    return detail


@router.get("/{project_id}/materials/{material_id}/document", response_model=DocumentDetailRead)
def get_document(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> DocumentDetailRead:
    material, document, chunk_count, image_count = MaterialService(session).get_material_detail(
        user_id=user.id, project_id=project.id, material_id=material_id
    )
    if document is None:
        raise NotFoundError("Document is not ready yet.")
    doc_read = DocumentDetailRead.model_validate(document)
    doc_read.chunk_count = chunk_count
    doc_read.image_count = image_count
    return doc_read


@router.get("/{project_id}/materials/{material_id}/document/chunks", response_model=Page[ChunkRead])
def list_chunks(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ChunkRead]:
    items, total, _ = MaterialService(session).list_document_chunks(
        user_id=user.id,
        project_id=project.id,
        material_id=material_id,
        page=page,
        page_size=page_size,
    )
    return Page[ChunkRead](
        items=[ChunkRead.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}/materials/{material_id}/images", response_model=Page[DocumentImageRead])
def list_images(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Page-ordered extracted-image metadata (no binaries, no storage keys)."""
    items, total = MaterialService(session).list_document_images(
        user_id=user.id,
        project_id=project.id,
        material_id=material_id,
        page=page,
        page_size=page_size,
    )
    return Page[DocumentImageRead](
        items=[DocumentImageRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{project_id}/materials/{material_id}/images/{image_id}",
    response_model=DocumentImageRead,
)
def get_image(
    material_id: uuid.UUID,
    image_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
):
    image = MaterialService(session).get_document_image(
        user_id=user.id, project_id=project.id, material_id=material_id, image_id=image_id
    )
    return DocumentImageRead.model_validate(image)


@router.get("/{project_id}/materials/{material_id}/images/{image_id}/content")
def get_image_content(
    material_id: uuid.UUID,
    image_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
):
    """Image bytes through the authenticated API (bucket stays private; no
    signed URLs, no storage keys)."""
    from fastapi import Response

    data, mime_type = MaterialService(session).get_image_bytes(
        user_id=user.id, project_id=project.id, material_id=material_id, image_id=image_id
    )
    return Response(content=data, media_type=mime_type)


"""Original-PDF content endpoint (authenticated; bucket stays private)."""


@router.get("/{project_id}/materials/{material_id}/content")
def get_material_content(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
):
    """Original PDF bytes through the authenticated API so the frontend can
    render an in-browser preview. Bucket stays private (no signed URLs, no
    storage keys); served inline for <embed>/<iframe> viewing."""
    from urllib.parse import quote

    from fastapi import Response

    data, mime_type, filename = MaterialService(session).get_material_bytes(
        user_id=user.id, project_id=project.id, material_id=material_id
    )
    safe = quote(filename or "document.pdf")
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{safe}"'},
    )


@router.post("/{project_id}/materials/{material_id}/reprocess", response_model=MaterialRead)
def reprocess_material(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> MaterialRead:
    material = MaterialService(session).reprocess_material(
        user_id=user.id, project_id=project.id, material_id=material_id
    )
    dispatch_processing(material.id)
    return MaterialRead.model_validate(material)


@router.delete("/{project_id}/materials/{material_id}", response_model=MaterialRead)
def archive_material(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> MaterialRead:
    """Archive (soft-delete). Storage object, Document, chunks, and events are
    kept so restores are lossless."""
    material = MaterialService(session).archive_material(
        user_id=user.id, project_id=project.id, material_id=material_id
    )
    return MaterialRead.model_validate(material)


@router.post("/{project_id}/materials/{material_id}/restore", response_model=MaterialRead)
def restore_material(
    material_id: uuid.UUID,
    project: OwnedProject,
    user: CurrentUser,
    session: SessionDep,
) -> MaterialRead:
    material = MaterialService(session).restore_material(
        user_id=user.id, project_id=project.id, material_id=material_id
    )
    return MaterialRead.model_validate(material)
