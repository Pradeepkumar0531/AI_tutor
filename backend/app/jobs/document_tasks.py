"""Document processing worker task: Material QUEUED -> PROCESSING -> READY/FAILED.

Runs in a Celery worker process with zero request context: it builds its own
DB session, storage backend, and OCR provider from Settings + the persisted
Material row. The browser may be long closed — everything needed is durable.

Concurrency: exactly one worker owns a material at a time via an atomic
``UPDATE ... WHERE status IN (QUEUED, RETRYING)`` claim on the ProcessingJob
row (works across processes on PostgreSQL and SQLite; no memory locks, no
Redis flags). A RUNNING claim older than ``processing_stale_claim_minutes``
is treated as crashed and may be reclaimed.

Idempotency: the Document rebuild (delete-then-insert in one transaction) plus
the unique constraint on ``documents.material_id`` means re-execution never
duplicates Documents or chunks; an already-complete READY material is a no-op
that emits no duplicate events.
"""

from __future__ import annotations

import logging
import time
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.documents.chunking import estimate_tokens
from app.documents.errors import PermanentFailure, TransientFailure
from app.documents.images import RawImage, build_image_storage_key
from app.documents.ocr import LazyOcrProvider, OcrProvider
from app.documents.pipeline import PipelineConfig, process_pdf
from app.jobs.celery_app import celery_app
from app.jobs.claim import claim_job, get_or_create_job, idempotency_key
from app.jobs.dispatch import dispatch_knowledge
from app.jobs.retry import NeedsRetry, retry_countdown
from app.models.enums import EventType, JobStatus, MaterialStatus
from app.models.materials import Document, DocumentChunk, DocumentImage, Material
from app.models.mixins import utcnow
from app.models.ops import ProcessingJob
from app.repositories.intelligence import EventRepository
from app.services.knowledge_service import KnowledgeService
from app.storage import ObjectNotFoundError, StorageError, StorageService, get_storage_service

log = logging.getLogger("app.jobs.process_material")

TASK_NAME = "app.jobs.process_material"
JOB_TYPE = "document.process"


def _idempotency_key(material_id: uuid.UUID) -> str:
    return idempotency_key(material_id, suffix="process")


def _pipeline_config(settings: Settings) -> PipelineConfig:
    return PipelineConfig(
        max_pages=settings.processing_max_pages,
        max_chars=settings.processing_max_chars,
        chunk_size=settings.processing_chunk_size,
        chunk_overlap=settings.processing_chunk_overlap,
        min_chunk_chars=settings.processing_min_chunk_chars,
        ocr_min_chars_per_page=settings.ocr_min_chars_per_page,
        ocr_enabled=settings.ocr_enabled,
        image_extraction_enabled=settings.pdf_image_extraction_enabled,
        min_image_width=settings.pdf_min_image_width,
        min_image_height=settings.pdf_min_image_height,
        min_image_bytes=settings.pdf_min_image_bytes,
        max_images_per_page=settings.pdf_max_images_per_page,
        max_images_per_document=settings.pdf_max_images_per_document,
    )


def _emit(
    session: Session,
    *,
    event_type: EventType,
    user_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    material: Material,
    extra: dict | None = None,
) -> None:
    payload = {"material_id": str(material.id), "name": material.name}
    if extra:
        payload.update(extra)
    EventRepository(session).append(
        event_type=event_type,
        user_id=user_id,
        project_id=project_id,
        entity_type="material",
        entity_id=material.id,
        payload=payload,
    )


def _reload(session: Session, material_id: uuid.UUID) -> tuple[Material, ProcessingJob]:
    """Re-attach after a rollback. Both rows predate the claim and rollbacks
    never delete them, so absence is a bug, not a state."""
    material = session.get(Material, material_id)
    job = session.scalar(
        sa.select(ProcessingJob).where(
            ProcessingJob.idempotency_key == _idempotency_key(material_id)
        )
    )
    assert material is not None and job is not None
    return material, job


def _fail(
    session: Session,
    *,
    material: Material,
    job: ProcessingJob,
    user_id: uuid.UUID | None,
    user_message: str,
    detail: str,
) -> dict:
    now = utcnow()
    material.status = MaterialStatus.FAILED
    material.processing_error = user_message
    material.processing_completed_at = now
    job.status = JobStatus.FAILED
    job.error = detail or user_message
    job.completed_at = now
    _emit(
        session,
        event_type=EventType.MATERIAL_FAILED,
        user_id=user_id,
        project_id=material.project_id,
        material=material,
        extra={"error": user_message},
    )
    session.commit()
    log.warning(
        "processing failed material_id=%s project_id=%s job_id=%s err=%s",
        material.id,
        material.project_id,
        job.id,
        detail or user_message,
    )
    return {"status": "FAILED", "material_id": str(material.id), "error": user_message}


def execute_material_processing(
    material_id: uuid.UUID,
    *,
    session: Session,
    settings: Settings,
    storage: StorageService,
    ocr_provider_factory=None,  # () -> OcrProvider | None; overridable in tests
) -> dict:
    """Run the full pipeline for one material. Raises ``NeedsRetry`` when the
    worker should retry with backoff; returns a summary dict otherwise."""
    material = session.get(Material, material_id)
    if material is None:
        log.info("material gone, skipping material_id=%s", material_id)
        return {"status": "skipped", "reason": "material-missing"}

    project_id = material.project_id
    user_id = material.project.owner_id if material.project else None

    job = get_or_create_job(
        session,
        job_type=JOB_TYPE,
        project_id=project_id,
        material_id=material.id,
        idempotency_key=_idempotency_key(material.id),
    )

    # Fast idempotent path: already complete with content -> no-op, no events.
    if material.status == MaterialStatus.READY:
        existing = session.scalar(sa.select(Document).where(Document.material_id == material.id))
        if existing is not None:
            chunks = (
                session.scalar(
                    sa.select(sa.func.count(DocumentChunk.id)).where(
                        DocumentChunk.document_id == existing.id
                    )
                )
                or 0
            )
            if chunks > 0:
                log.info("already complete, skipping material_id=%s", material.id)
                return {"status": "already-done", "material_id": str(material.id)}

    # Atomic claim: exactly one worker proceeds (fresh queue/retry, or stale lease).
    if not claim_job(session, job, settings):
        log.info(
            "claim lost (another worker owns it) material_id=%s job_id=%s", material.id, job.id
        )
        session.rollback()
        return {"status": "skipped", "reason": "already-claimed"}
    session.refresh(job)
    attempt = job.attempt_count

    material.status = MaterialStatus.PROCESSING
    material.processing_started_at = utcnow()
    material.processing_completed_at = None
    material.processing_error = None
    material.retry_count = attempt
    _emit(
        session,
        event_type=EventType.MATERIAL_PROCESSING_STARTED,
        user_id=user_id,
        project_id=project_id,
        material=material,
        extra={"attempt": attempt},
    )
    session.commit()
    log.info(
        "processing started material_id=%s project_id=%s job_id=%s attempt=%s",
        material.id,
        project_id,
        job.id,
        attempt,
    )

    run_started = time.perf_counter()
    try:
        if not material.storage_key:
            raise _StorageMissing()
        try:
            data = storage.get(material.storage_key)
        except ObjectNotFoundError as e:
            raise _StorageMissing(detail=str(e)) from e
        provider: OcrProvider | None
        if ocr_provider_factory is not None:
            provider = ocr_provider_factory()
        else:
            provider = LazyOcrProvider()
        result = process_pdf(data, _pipeline_config(settings), provider)
    except PermanentFailure as e:
        session.rollback()
        material, job = _reload(session, material_id)
        return _fail(
            session,
            material=material,
            job=job,
            user_id=user_id,
            user_message=e.user_message,
            detail=e.detail,
        )
    except (TransientFailure, StorageError, OperationalError, OSError) as e:
        session.rollback()
        material, job = _reload(session, material_id)
        if attempt >= job.max_retries:
            return _fail(
                session,
                material=material,
                job=job,
                user_id=user_id,
                user_message=(
                    "Processing failed after several attempts. Please try reprocessing later."
                ),
                detail=f"{type(e).__name__}: {e}",
            )
        job.status = JobStatus.RETRYING
        job.error = f"{type(e).__name__}: {e}"
        session.commit()
        raise NeedsRetry(e, retry_countdown(attempt)) from e
    except Exception as e:  # noqa: BLE001 - unexpected bugs retry bounded, then fail
        log.exception("unexpected processing error material_id=%s", material_id)
        session.rollback()
        live_job = session.get(ProcessingJob, job.id)
        assert live_job is not None
        if attempt < live_job.max_retries:
            live_job.status = JobStatus.RETRYING
            live_job.error = f"{type(e).__name__}: {e}"
            session.commit()
            raise NeedsRetry(e, retry_countdown(attempt)) from e
        material, job = _reload(session, material_id)
        return _fail(
            session,
            material=material,
            job=job,
            user_id=user_id,
            user_message="Processing failed unexpectedly. Please try reprocessing later.",
            detail=f"{type(e).__name__}: {e}",
        )

    # Persist: delete-then-insert rebuild in ONE transaction (idempotent).
    # Images persist in the same transaction: a material is never READY while
    # image metadata/storage is partial.
    put_keys: list[str] = []
    old_image_keys: list[str] = []
    try:
        old = session.scalar(sa.select(Document).where(Document.material_id == material.id))
        if old is not None:
            old_image_keys = [image.storage_key for image in old.images]
            session.delete(old)
            session.flush()
        document = Document(
            material_id=material.id,
            project_id=project_id,
            page_count=result.page_count,
            extraction_method=result.extraction_method,
            doc_metadata={
                **result.doc_metadata,
                "char_count": result.char_count,
                "chunk_count": result.chunk_count,
                "duration_ms": result.duration_ms + int((time.perf_counter() - run_started) * 1000),
            },
        )
        session.add(document)
        session.flush()  # document.id for chunk rows
        for chunk in result.chunks:
            session.add(
                DocumentChunk(
                    document_id=document.id,
                    project_id=project_id,
                    chunk_index=chunk.index,
                    content=chunk.content,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    token_count=estimate_tokens(chunk.content),
                    embedding=None,  # Prompt 6 owns embeddings. Never set here.
                    chunk_metadata={**chunk.metadata, "source": "text-extraction"},
                )
            )
        image_stats = _persist_document_images(
            session,
            storage,
            project_id=project_id,
            material=material,
            document=document,
            images=result.images,
            put_keys=put_keys,
        )
        now = utcnow()
        material.status = MaterialStatus.READY
        material.processing_completed_at = now
        material.processing_error = None
        job.status = JobStatus.SUCCEEDED
        job.error = None
        job.completed_at = now
        _emit(
            session,
            event_type=EventType.MATERIAL_READY,
            user_id=user_id,
            project_id=project_id,
            material=material,
            extra={
                "pages": result.page_count,
                "chunks": result.chunk_count,
                "chars": result.char_count,
                "ocr_pages": result.ocr_page_count,
                "images": image_stats["stored"],
                "image_duplicates": image_stats["duplicates"],
            },
        )
        session.commit()
    except IntegrityError as e:
        # Lost a rebuild race (unique documents.material_id): the winner's
        # data stands; treat as success without duplicating anything.
        session.rollback()
        _delete_orphan_image_keys(session, storage, put_keys)
        log.warning("rebuild race lost material_id=%s err=%s", material_id, e)
        return {"status": "already-done", "material_id": str(material_id)}
    except StorageError as e:
        # Image puts share the transient policy of the PDF read above: retry
        # bounded, then fail honestly. Just-put keys are cleaned best-effort.
        session.rollback()
        _delete_orphan_image_keys(session, storage, put_keys)
        material, job = _reload(session, material_id)
        if attempt >= job.max_retries:
            return _fail(
                session,
                material=material,
                job=job,
                user_id=user_id,
                user_message=(
                    "Processing failed after several attempts. Please try reprocessing later."
                ),
                detail=f"{type(e).__name__}: {e}",
            )
        job.status = JobStatus.RETRYING
        job.error = f"{type(e).__name__}: {e}"
        session.commit()
        raise NeedsRetry(e, retry_countdown(attempt)) from e
    _delete_orphan_image_keys(session, storage, old_image_keys)
    log.info(
        "PDF image extraction completed: material_id=%s document_id=%s "
        "project_id=%s pages=%s extracted=%s stored=%s duplicates=%s filtered=%s",
        material.id,
        document.id,
        project_id,
        result.page_count,
        len(result.images),
        image_stats["stored"],
        image_stats["duplicates"],
        result.image_stats.get("filtered", 0),
    )
    log.info(
        "processing ready material_id=%s project_id=%s pages=%s chunks=%s "
        "ocr_pages=%s duration_ms=%s",
        material.id,
        project_id,
        result.page_count,
        result.chunk_count,
        result.ocr_page_count,
        result.duration_ms,
    )
    return {
        "status": "READY",
        "material_id": str(material.id),
        "pages": result.page_count,
        "chunks": result.chunk_count,
        "ocr_pages": result.ocr_page_count,
        "images": image_stats["stored"],
    }


def _persist_document_images(
    session: Session,
    storage: StorageService,
    *,
    project_id: uuid.UUID,
    material: Material,
    document: Document,
    images: list[RawImage],
    put_keys: list[str],
) -> dict[str, int]:
    """Store unique image binaries (content-keyed, idempotent puts) and one
    row per page occurrence (provenance preserved). Runs inside the caller's
    persist transaction: StorageError propagates to the retry/fail path, and
    ``put_keys`` lets the caller clean just-written objects on rollback."""
    unique: dict[str, tuple[str, bytes, str]] = {}
    for image in images:
        key = build_image_storage_key(
            project_id=project_id,
            material_id=material.id,
            sha256=image.sha256,
            ext=image.ext,
        )
        unique.setdefault(image.sha256, (key, image.data, image.mime_type))
    for key, data, content_type in unique.values():
        storage.put(key, data, content_type)
        put_keys.append(key)
    keys = {sha: key for sha, (key, _, _) in unique.items()}
    for image in images:
        session.add(
            DocumentImage(
                document_id=document.id,
                material_id=material.id,
                project_id=project_id,
                page_number=image.page_number,
                image_index=image.image_index,
                width=image.width,
                height=image.height,
                mime_type=image.mime_type,
                file_size=image.size_bytes,
                storage_key=keys[image.sha256],
                sha256=image.sha256,
            )
        )
    return {"stored": len(unique), "duplicates": len(images) - len(unique)}


def _delete_orphan_image_keys(session: Session, storage: StorageService, keys: list[str]) -> None:
    """Best-effort removal of image objects no row references anymore (failed
    persists, superseded rebuilds). Never raises: cleanup must not fail work."""
    for key in dict.fromkeys(keys):
        try:
            refs = (
                session.scalar(
                    sa.select(sa.func.count(DocumentImage.id)).where(
                        DocumentImage.storage_key == key
                    )
                )
                or 0
            )
            if refs == 0:
                storage.delete(key)
        except Exception as e:  # noqa: BLE001 - best effort only
            log.warning("orphan image cleanup failed key=%s err=%s", key, e)


class _StorageMissing(PermanentFailure):
    def __init__(self, detail: str = "") -> None:
        super().__init__(
            "The uploaded file is missing from storage. Please re-upload the material.",
            detail=detail,
        )


@celery_app.task(
    name=TASK_NAME,
    bind=True,
    autoretry_for=(),  # retries are controlled explicitly in execute_* (no infinite loops)
    max_retries=3,
)
def process_material(self, material_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Celery entrypoint: build worker-local deps, execute, translate retries."""
    settings = get_settings()
    factory = get_session_factory()
    if factory is None:  # pragma: no cover - worker always has DATABASE_URL
        raise TransientFailure("Database is not configured.")
    session = factory()
    try:
        storage = get_storage_service()
        result = execute_material_processing(
            uuid.UUID(material_id), session=session, settings=settings, storage=storage
        )
        if isinstance(result, dict) and result.get("status") == "READY":
            _chain_knowledge(session, settings, uuid.UUID(material_id))
        return result
    except NeedsRetry as e:
        raise self.retry(exc=e.cause, countdown=e.countdown) from e.cause
    finally:
        session.close()


def _chain_knowledge(session: Session, settings: Settings, material_id: uuid.UUID) -> None:
    """Enqueue knowledge processing for freshly READY material. The knowledge
    job row is created here (same committed session); broker dispatch is
    best-effort so a down broker never fails the document task."""
    material = session.get(Material, material_id)
    if material is None:
        return
    KnowledgeService(session, settings).ensure_knowledge_job(
        project_id=material.project_id, material_id=material.id
    )
    session.commit()
    dispatch_knowledge(material.id)
