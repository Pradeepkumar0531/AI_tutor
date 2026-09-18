"""Knowledge worker task: READY material -> embeddings -> concepts.

Runs in a Celery worker with zero request context (same pattern as document
processing): own DB session, providers built from Settings + the persisted
Material row. Async provider calls are bridged with ``asyncio.run`` per batch.

Idempotency: chunks with vectors are skipped (resume), concept upserts are
name-scoped merges, relationships are pre-checked + savepoint-guarded, and a
fully embedded material with concepts is a no-op emitting no events.
Knowledge failure never regresses the material document state (stays READY).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

import sqlalchemy as sa
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.ai.errors import (
    AITransientError,
    ConceptExtractionFailed,
    EmbeddingConfigurationError,
    EmbeddingDimensionMismatch,
    EmbeddingProviderUnavailable,
    EmbeddingResponseInvalid,
    KnowledgeProcessingFailed,
)
from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.jobs.celery_app import celery_app
from app.jobs.claim import claim_job, get_or_create_job, idempotency_key
from app.jobs.retry import NeedsRetry, retry_countdown
from app.models.enums import EventType, JobStatus, MaterialStatus
from app.models.knowledge import Concept
from app.models.materials import Document, DocumentChunk, Material
from app.models.mixins import utcnow
from app.models.ops import ProcessingJob
from app.repositories.intelligence import EventRepository
from app.repositories.materials import ChunkRepository
from app.services.knowledge_service import KNOWLEDGE_JOB_TYPE

log = logging.getLogger("app.jobs.process_knowledge")

TASK_NAME = "app.jobs.process_knowledge"

TRANSIENT = (
    EmbeddingProviderUnavailable,
    AITransientError,
    TimeoutError,
    asyncio.TimeoutError,
    OperationalError,
    OSError,
)
PERMANENT = (
    EmbeddingConfigurationError,
    EmbeddingDimensionMismatch,
    EmbeddingResponseInvalid,
    ConceptExtractionFailed,
    KnowledgeProcessingFailed,
)


def _knowledge_key(material_id: uuid.UUID) -> str:
    return idempotency_key(material_id, suffix="knowledge")


def _emit(
    session: Session,
    *,
    event_type: EventType,
    user_id: uuid.UUID | None,
    project_id: uuid.UUID,
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


def _fail_knowledge(
    session: Session,
    *,
    material: Material,
    job: ProcessingJob,
    user_id: uuid.UUID | None,
    user_message: str,
    detail: str,
) -> dict:
    """Fail the knowledge job. The document stays READY — knowledge failure
    must never destroy completed extraction work."""
    now = utcnow()
    job.status = JobStatus.FAILED
    job.error = detail or user_message
    job.completed_at = now
    _emit(
        session,
        event_type=EventType.EMBEDDING_FAILED,
        user_id=user_id,
        project_id=material.project_id,
        material=material,
        extra={"error": user_message},
    )
    session.commit()
    log.warning(
        "knowledge failed material_id=%s project_id=%s job_id=%s err=%s",
        material.id,
        material.project_id,
        job.id,
        detail or user_message,
    )
    return {"status": "FAILED", "material_id": str(material.id), "error": user_message}


def _reload_knowledge(session: Session, material_id: uuid.UUID) -> tuple[Material, ProcessingJob]:
    material = session.get(Material, material_id)
    job = session.scalar(
        sa.select(ProcessingJob).where(ProcessingJob.idempotency_key == _knowledge_key(material_id))
    )
    assert material is not None and job is not None
    return material, job


def execute_knowledge_processing(
    material_id: uuid.UUID,
    *,
    session: Session,
    settings: Settings,
    ai_service=None,
) -> dict:
    """Embed missing chunks, then extract concepts. Raises ``NeedsRetry`` for
    transient failures; returns a summary dict otherwise."""
    from app.ai.service import ai_service as default_ai_service

    ai = ai_service or default_ai_service
    material = session.get(Material, material_id)
    if material is None:
        log.info("material gone, skipping knowledge material_id=%s", material_id)
        return {"status": "skipped", "reason": "material-missing"}
    if material.status != MaterialStatus.READY:
        log.info(
            "material not READY, skipping knowledge material_id=%s status=%s",
            material_id,
            material.status,
        )
        return {"status": "skipped", "reason": "not-ready"}

    project_id = material.project_id
    user_id = material.project.owner_id if material.project else None
    document = session.scalar(sa.select(Document).where(Document.material_id == material.id))
    if document is None:
        log.warning("READY material without document material_id=%s", material_id)
        return {"status": "skipped", "reason": "no-document"}

    job = get_or_create_job(
        session,
        job_type=KNOWLEDGE_JOB_TYPE,
        project_id=project_id,
        material_id=material.id,
        idempotency_key=_knowledge_key(material.id),
    )

    # Fast idempotent path: everything embedded and concepts present.
    chunks_repo = ChunkRepository(session)
    total, embedded = chunks_repo.count_embedded_for_material(material.id)
    concepts_existing = (
        session.scalar(sa.select(sa.func.count(Concept.id)).where(Concept.project_id == project_id))
        or 0
    )
    if total > 0 and embedded == total and concepts_existing > 0:
        log.info("knowledge complete, skipping material_id=%s", material.id)
        return {"status": "already-done", "material_id": str(material.id)}

    if not claim_job(session, job, settings):
        log.info("knowledge claim lost material_id=%s job_id=%s", material.id, job.id)
        session.rollback()
        return {"status": "skipped", "reason": "already-claimed"}
    session.refresh(job)
    attempt = job.attempt_count

    _emit(
        session,
        event_type=EventType.EMBEDDING_STARTED,
        user_id=user_id,
        project_id=project_id,
        material=material,
        extra={"attempt": attempt},
    )
    session.commit()
    log.info(
        "knowledge started material_id=%s project_id=%s job_id=%s attempt=%s",
        material.id,
        project_id,
        job.id,
        attempt,
    )

    embedding_service = ai.embedding_service(settings)
    embedded_this_run = 0
    batches = 0
    try:
        for _round in range(100):  # bounded resume loop; each round commits
            pending = chunks_repo.list_unembedded(document.id, project_id, limit=500)
            if not pending:
                break
            batch_size = max(1, settings.embedding_batch_size)
            batch = pending[:batch_size]
            embed_started = time.perf_counter()
            vectors = asyncio.run(embedding_service.embed_texts([c.content for c in batch]))
            from app.services.ai_usage_service import AiUsageService

            AiUsageService(session).record(
                feature="knowledge_embed",
                provider=getattr(embedding_service, "name", "embeddings"),
                model=settings.google_embedding_model,
                latency_ms=int((time.perf_counter() - embed_started) * 1000),
                user_id=user_id,
                project_id=project_id,
            )
            chunks_repo.write_embeddings([(c.id, v) for c, v in zip(batch, vectors, strict=True)])
            session.flush()
            session.commit()
            embedded_this_run += len(batch)
            batches += 1
        else:
            raise KnowledgeProcessingFailed("Embedding did not converge after 100 batches.")
    except PERMANENT as e:
        session.rollback()
        material, job = _reload_knowledge(session, material_id)
        return _fail_knowledge(
            session,
            material=material,
            job=job,
            user_id=user_id,
            user_message="Knowledge processing failed. Please try again later.",
            detail=f"{type(e).__name__}: {e}",
        )
    except TRANSIENT as e:
        session.rollback()
        material, job = _reload_knowledge(session, material_id)
        if attempt >= job.max_retries:
            return _fail_knowledge(
                session,
                material=material,
                job=job,
                user_id=user_id,
                user_message="Knowledge processing failed after several attempts.",
                detail=f"{type(e).__name__}: {e}",
            )
        job.status = JobStatus.RETRYING
        job.error = f"{type(e).__name__}: {e}"
        session.commit()
        raise NeedsRetry(e, retry_countdown(attempt)) from e
    except Exception as e:  # noqa: BLE001 - unexpected bugs retry bounded, then fail
        log.exception("unexpected knowledge error material_id=%s", material_id)
        session.rollback()
        material, job = _reload_knowledge(session, material_id)
        if attempt < job.max_retries:
            job.status = JobStatus.RETRYING
            job.error = f"{type(e).__name__}: {e}"
            session.commit()
            raise NeedsRetry(e, retry_countdown(attempt)) from e
        return _fail_knowledge(
            session,
            material=material,
            job=job,
            user_id=user_id,
            user_message="Knowledge processing failed unexpectedly.",
            detail=f"{type(e).__name__}: {e}",
        )

    # ---- concepts (embeddings are durable now; failure here keeps them) ----
    try:
        stats = _extract_concepts(session, settings, ai, material, project_id, user_id)
    except PERMANENT as e:
        session.rollback()
        material, job = _reload_knowledge(session, material_id)
        return _fail_knowledge(
            session,
            material=material,
            job=job,
            user_id=user_id,
            user_message="Concept extraction failed. Embeddings were kept.",
            detail=f"{type(e).__name__}: {e}",
        )
    except TRANSIENT as e:
        session.rollback()
        material, job = _reload_knowledge(session, material_id)
        if attempt >= job.max_retries:
            return _fail_knowledge(
                session,
                material=material,
                job=job,
                user_id=user_id,
                user_message="Concept extraction failed after several attempts.",
                detail=f"{type(e).__name__}: {e}",
            )
        job.status = JobStatus.RETRYING
        job.error = f"{type(e).__name__}: {e}"
        session.commit()
        raise NeedsRetry(e, retry_countdown(attempt)) from e
    except Exception as e:  # noqa: BLE001
        log.exception("unexpected concept error material_id=%s", material_id)
        session.rollback()
        material, job = _reload_knowledge(session, material_id)
        if attempt < job.max_retries:
            job.status = JobStatus.RETRYING
            job.error = f"{type(e).__name__}: {e}"
            session.commit()
            raise NeedsRetry(e, retry_countdown(attempt)) from e
        return _fail_knowledge(
            session,
            material=material,
            job=job,
            user_id=user_id,
            user_message="Concept extraction failed unexpectedly.",
            detail=f"{type(e).__name__}: {e}",
        )

    now = utcnow()
    job.status = JobStatus.SUCCEEDED
    job.error = None
    job.completed_at = now
    _emit(
        session,
        event_type=EventType.EMBEDDING_COMPLETED,
        user_id=user_id,
        project_id=project_id,
        material=material,
        extra={"embedded": embedded_this_run, "batches": batches},
    )
    _emit(
        session,
        event_type=EventType.CONCEPTS_EXTRACTED,
        user_id=user_id,
        project_id=project_id,
        material=material,
        extra={
            "concepts_created": stats.created,
            "concepts_updated": stats.updated,
            "relationships": stats.relationships_created,
        },
    )
    session.commit()
    log.info(
        "knowledge ready material_id=%s project_id=%s embedded=%s concepts=%s rels=%s",
        material.id,
        project_id,
        embedded_this_run,
        stats.created,
        stats.relationships_created,
    )
    return {
        "status": "READY",
        "material_id": str(material.id),
        "embedded": embedded_this_run,
        "concepts_created": stats.created,
        "relationships_created": stats.relationships_created,
    }


def _gather_concept_input(
    session: Session, *, project_id: uuid.UUID, material_id: uuid.UUID, max_chars: int
) -> tuple[str, list[uuid.UUID], list[int]]:
    """Deterministic extraction input: all embedded chunks in index order,
    truncated to budget. Returns (text, chunk_ids, pages)."""
    rows = list(
        session.scalars(
            sa.select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.material_id == material_id,
                DocumentChunk.project_id == project_id,
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(DocumentChunk.chunk_index)
        )
    )
    parts: list[str] = []
    chunk_ids: list[uuid.UUID] = []
    pages: set[int] = set()
    total = 0
    for chunk in rows:
        block = f"[chunk {chunk.chunk_index}] {chunk.content}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
        chunk_ids.append(chunk.id)
        if chunk.page_start is not None:
            pages.add(chunk.page_start)
        if chunk.page_end is not None:
            pages.add(chunk.page_end)
    return "\n\n".join(parts), chunk_ids, sorted(pages)


def _extract_concepts(
    session: Session,
    settings: Settings,
    ai,
    material: Material,
    project_id: uuid.UUID,
    user_id: uuid.UUID | None,
):
    from app.services.knowledge_service import KnowledgeService, ProvenanceEntry

    extractor = ai.concept_extractor(settings)
    source_text, chunk_ids, pages = _gather_concept_input(
        session,
        project_id=project_id,
        material_id=material.id,
        max_chars=settings.concept_max_input_chars,
    )
    if not source_text.strip():
        from app.ai.errors import ConceptExtractionFailed

        raise ConceptExtractionFailed("No embedded content available for concept extraction.")
    extract_started = time.perf_counter()
    result = asyncio.run(extractor.extract(source_text, max_concepts=settings.concept_max_per_run))
    from app.services.ai_usage_service import AiUsageService

    AiUsageService(session).record(
        feature="concept_extract",
        provider=getattr(extractor, "name", "concepts"),
        model=settings.groq_model_concepts if not settings.test_fake_ai else "fake-concepts",
        latency_ms=int((time.perf_counter() - extract_started) * 1000),
        user_id=user_id,
        project_id=project_id,
    )
    service = KnowledgeService(session, settings, ai)
    return service.upsert_concepts(
        project_id=project_id,
        extraction=result,
        provenance=ProvenanceEntry(
            material_id=material.id,
            material_name=material.name,
            chunk_ids=chunk_ids,
            pages=pages,
        ),
        model=settings.groq_model_concepts if not settings.test_fake_ai else "fake-concepts",
        max_concepts=settings.concept_max_per_run,
    )


@celery_app.task(
    name=TASK_NAME,
    bind=True,
    autoretry_for=(),  # retries are controlled explicitly in execute_* (no infinite loops)
    max_retries=3,
)
def process_knowledge(self, material_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Celery entrypoint: build worker-local deps, execute, translate retries."""
    settings = get_settings()
    factory = get_session_factory()
    if factory is None:  # pragma: no cover - worker always has DATABASE_URL
        from app.documents.errors import TransientFailure

        raise TransientFailure("Database is not configured.")
    from app.ai.service import ai_service

    session = factory()
    try:
        return execute_knowledge_processing(
            uuid.UUID(material_id), session=session, settings=settings, ai_service=ai_service
        )
    except NeedsRetry as e:
        raise self.retry(exc=e.cause, countdown=e.countdown) from e.cause
    finally:
        session.close()
