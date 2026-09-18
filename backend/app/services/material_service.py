"""Material service: upload orchestration, lifecycle reads, reprocess, archive.

Consistency model (documented, not pretended): object storage and PostgreSQL
cannot share one atomic transaction. Order is validate -> persist object ->
persist rows (one DB transaction) -> enqueue Celery *after commit* (routes call
``dispatch_processing`` post-return). If the DB transaction fails after the
object write, a compensating delete removes the orphaned object best-effort.
If the broker is down, the job row stays QUEUED and a worker (or reprocess)
picks it up later — the upload still returns 201.
"""

from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.documents.validation import build_storage_key, validate_pdf_upload
from app.models.enums import EventType, JobStatus, MaterialStatus
from app.models.materials import Document, DocumentChunk, Material
from app.repositories.intelligence import EventRepository
from app.repositories.materials import (
    ChunkRepository,
    DocumentImageRepository,
    DocumentRepository,
    MaterialRepository,
    ProcessingJobRepository,
)
from app.repositories.projects import ProjectRepository
from app.services.base import BaseService, transactional
from app.storage import get_storage_service

log = logging.getLogger("app.services.materials")


class MaterialService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.materials = MaterialRepository(session)
        self.documents = DocumentRepository(session)
        self.chunks = ChunkRepository(session)
        self.images = DocumentImageRepository(session)
        self.jobs = ProcessingJobRepository(session)
        self.events = EventRepository(session)
        self.projects = ProjectRepository(session)

    # ------------------------------------------------------------- upload

    @transactional
    def upload_material(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        filename: str | None,
        content_type: str | None,
        data: bytes,
        title: str | None = None,
    ) -> Material:
        settings = get_settings()
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        validated = validate_pdf_upload(
            filename=filename,
            content_type=content_type,
            data=data,
            max_bytes=settings.max_upload_bytes,
        )
        storage = get_storage_service()
        material = self.materials.create(
            project_id=project.id,
            name=(title.strip() if title and title.strip() else validated.filename),
            original_filename=validated.filename,
            mime_type=validated.content_type,
            file_size=validated.size_bytes,
            checksum=validated.sha256,
        )
        material.storage_provider = storage.provider
        self.session.flush()  # id needed for the server-side storage key
        key = build_storage_key(project_id=project.id, material_id=material.id)
        try:
            storage.put(key, data, content_type=validated.content_type)
            material.storage_key = key
            self.session.flush()
            self.jobs.enqueue(
                job_type="document.process",
                project_id=project.id,
                material_id=material.id,
                idempotency_key=f"material:{material.id}:process",
                payload={"material_id": str(material.id)},
            )
            self.events.append(
                event_type=EventType.MATERIAL_UPLOADED,
                user_id=user_id,
                project_id=project.id,
                entity_type="material",
                entity_id=material.id,
                payload={"name": material.name, "size_bytes": validated.size_bytes},
            )
        except Exception:
            # Compensating cleanup: the DB transaction will roll back (via
            # @transactional); remove the orphaned object best-effort.
            try:
                storage.delete(key)
            except Exception as cleanup_error:  # noqa: BLE001
                log.warning("orphan storage cleanup failed key=%s err=%s", key, cleanup_error)
            raise
        return material

    # ------------------------------------------------------------- reads

    def list_materials(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: MaterialStatus | None = None,
        include_archived: bool = False,
    ) -> tuple[list[Material], int, dict[uuid.UUID, int | None], dict[uuid.UUID, int]]:
        """Scoped list plus per-material page/chunk counts from two GROUP BY
        queries (no N+1, no giant joins)."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        items, total = self.materials.list_for_project(
            project.id,
            status=status,
            page=page,
            page_size=page_size,
            include_archived=include_archived,
        )
        ids = [m.id for m in items]
        page_counts: dict[uuid.UUID, int | None] = {}
        chunk_counts: dict[uuid.UUID, int] = {}
        if ids:
            page_counts = {
                mid: pages
                for mid, pages in self.session.execute(
                    sa.select(Document.material_id, Document.page_count).where(
                        Document.material_id.in_(ids)
                    )
                ).all()
            }
            chunk_counts = {
                mid: count
                for mid, count in self.session.execute(
                    sa.select(Document.material_id, func.count(DocumentChunk.id))
                    .join(DocumentChunk, DocumentChunk.document_id == Document.id)
                    .where(Document.material_id.in_(ids))
                    .group_by(Document.material_id)
                ).all()
            }
        return items, total, page_counts, chunk_counts

    def get_material_detail(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> tuple[Material, Document | None, int, int]:
        """Material + its document (if any) + chunk/image counts. 404 unless owned."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        document = self.documents.get_by_material(material.id, project.id)
        chunk_count = 0
        image_count = 0
        if document is not None:
            chunk_count = (
                self.session.scalar(
                    sa.select(func.count(DocumentChunk.id)).where(
                        DocumentChunk.document_id == document.id
                    )
                )
                or 0
            )
            image_count = self.images.count_for_document(document.id, project.id)
        return material, document, chunk_count, image_count

    def list_document_images(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        material_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ):
        """Page-ordered images for one owned material (404 unless owned)."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        document = self.documents.get_by_material(material.id, project.id)
        if document is None:
            return [], 0
        return self.images.list_for_document(
            document.id, project.id, page=page, page_size=page_size
        )

    def get_document_image(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        material_id: uuid.UUID,
        image_id: uuid.UUID,
    ):
        """One image verified against material + project (full auth chain)."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        image = self.images.get_for_material(image_id, material.id, project.id)
        if image is None:
            raise NotFoundError("Image not found.")
        return image

    def get_image_bytes(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        material_id: uuid.UUID,
        image_id: uuid.UUID,
    ) -> tuple[bytes, str]:
        """Image bytes + MIME through StorageService (bucket stays private).
        A missing object is a 404 with a logged error, never a key leak."""
        from app.storage import ObjectNotFoundError

        image = self.get_document_image(
            user_id=user_id, project_id=project_id, material_id=material_id, image_id=image_id
        )
        storage = get_storage_service()
        try:
            return storage.get(image.storage_key), image.mime_type
        except ObjectNotFoundError as e:
            log.error("image binary missing key=%s image_id=%s", image.storage_key, image.id)
            raise NotFoundError("Image content is not available.") from e

    def get_material_bytes(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        material_id: uuid.UUID,
    ) -> tuple[bytes, str, str | None]:
        """Original PDF bytes + MIME + filename for the in-browser viewer.

        Auth chain matches every other material read (user -> owned project ->
        project material). Storage keys never leave the server; a missing
        object is a 404, never a key leak."""
        from app.storage import ObjectNotFoundError

        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        if not material.storage_key:
            raise NotFoundError("File content is not available yet.")
        storage = get_storage_service()
        try:
            data = storage.get(material.storage_key)
        except ObjectNotFoundError as e:
            log.error(
                "material binary missing key=%s material_id=%s",
                material.storage_key,
                material.id,
            )
            raise NotFoundError("File content is not available.") from e
        return data, material.mime_type or "application/pdf", material.original_filename

    def list_document_chunks(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        material_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DocumentChunk], int, Document]:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        document = self.documents.get_by_material(material.id, project.id)
        if document is None:
            raise NotFoundError("Document is not ready yet.")
        stmt = (
            sa.select(DocumentChunk)
            .where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.project_id == project.id,
            )
            .order_by(DocumentChunk.chunk_index)
        )
        items, total = self.chunks.paginate(stmt, page=page, page_size=page_size)
        return items, total, document

    # ------------------------------------------------------------- reprocess

    @transactional
    def reprocess_material(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> Material:
        """Reset a FAILED material to QUEUED. Guards: owned, FAILED, no live job."""
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        if material.status != MaterialStatus.FAILED:
            raise ConflictError(
                f"Only FAILED materials can be reprocessed (status={material.status.value})."
            )
        if self.jobs.get_pending_for_material(material.id):
            raise ConflictError("A processing job is already pending for this material.")
        job = self.jobs.get_by_idempotency(f"material:{material.id}:process")
        if job is None:
            job = self.jobs.enqueue(
                job_type="document.process",
                project_id=project.id,
                material_id=material.id,
                idempotency_key=f"material:{material.id}:process",
                payload={"material_id": str(material.id)},
            )
        else:
            job.status = JobStatus.QUEUED
            job.error = None
            job.attempt_count = 0
            job.started_at = None
            job.completed_at = None
        material.status = MaterialStatus.QUEUED
        material.processing_error = None
        material.processing_started_at = None
        material.processing_completed_at = None
        return material

    # ------------------------------------------------------------- archive

    @transactional
    def archive_material(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> Material:
        """Archive (soft-delete). Storage object, Document, and chunks are kept
        so restores are lossless; audit history is untouched."""
        from app.models.mixins import utcnow

        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id)
        if material is None:
            raise NotFoundError("Material not found.")
        material.archived_at = utcnow()
        return material

    @transactional
    def restore_material(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, material_id: uuid.UUID
    ) -> Material:
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        material = self.materials.get_for_project(material_id, project.id, include_archived=True)
        if material is None:
            raise NotFoundError("Material not found.")
        material.archived_at = None
        return material
