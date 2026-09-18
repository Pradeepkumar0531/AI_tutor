"""Knowledge worker: embedding, concepts, retries, idempotency, crash resume.

The real ``execute_knowledge_processing`` runs against the shared SQLite
session with injected fake AI (deterministic, no credentials, no network) —
the same orchestration the Celery worker executes.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.ai.embeddings import EmbeddingService
from app.ai.errors import (
    ConceptExtractionFailed,
    EmbeddingConfigurationError,
    EmbeddingProviderUnavailable,
)
from app.ai.fakes import DeterministicEmbeddingProvider, NaiveKeywordConceptExtractor
from app.core.config import Settings
from app.jobs.knowledge_tasks import execute_knowledge_processing
from app.jobs.retry import NeedsRetry
from app.models.enums import EventType, JobStatus, MaterialStatus
from app.models.knowledge import Concept
from app.models.materials import Document, DocumentChunk, Material
from app.models.mixins import utcnow
from app.models.ops import Event, ProcessingJob
from app.repositories.materials import ChunkRepository
from app.services.knowledge_service import KNOWLEDGE_JOB_TYPE
from tests.conftest import make_project, make_user

TEXTS = [
    "Photosynthesis converts sunlight into chemical energy in green plants daily.",
    "Chlorophyll captures sunlight efficiently inside the green chloroplasts.",
    "Mitochondria release stored energy as ATP through cellular respiration.",
]


class FakeAI:
    """Test double for AIService: deterministic providers, no network."""

    def __init__(self, provider=None, extractor=None) -> None:
        self._provider = provider or DeterministicEmbeddingProvider(dimensions=768)
        self._extractor = extractor or NaiveKeywordConceptExtractor()

    def embedding_service(self, settings: Settings) -> EmbeddingService:
        return EmbeddingService(
            self._provider,
            model=settings.google_embedding_model,
            dimensions=settings.embedding_dimensions,
            batch_size=settings.embedding_batch_size,
            timeout_seconds=settings.embedding_timeout_seconds,
            max_retries=settings.embedding_max_retries,
        )

    def concept_extractor(self, settings: Settings):
        return self._extractor


def _fake_settings(**kwargs) -> Settings:
    kwargs.setdefault("test_fake_ai", True)
    return Settings(**kwargs)


def _ready_material(session: Session, texts: list[str] = TEXTS):
    owner = make_user(session)
    project = make_project(session, owner)
    from app.repositories.materials import MaterialRepository

    mat = MaterialRepository(session).create(project_id=project.id, name="Doc")
    mat.status = MaterialStatus.READY
    session.flush()
    doc = Document(material_id=mat.id, project_id=project.id, page_count=1)
    session.add(doc)
    session.flush()
    for i, text in enumerate(texts):
        session.add(
            DocumentChunk(
                document_id=doc.id,
                project_id=project.id,
                chunk_index=i,
                content=text,
                page_start=1,
                page_end=1,
                embedding=None,
            )
        )
    session.commit()
    return owner, project, mat


def _run(session, mat, ai=None, **kwargs):
    return execute_knowledge_processing(
        mat.id,
        session=session,
        settings=_fake_settings(**kwargs),
        ai_service=ai or FakeAI(),
    )


def _job(session: Session, mat: Material) -> ProcessingJob:
    return session.query(ProcessingJob).filter_by(material_id=mat.id).one()


def _events(session: Session, mat: Material, event_type: EventType) -> int:
    return (
        session.query(Event)
        .filter(Event.entity_id == mat.id, Event.event_type == event_type)
        .count()
    )


# ------------------------------------------------------------- happy path


def test_full_run_embeds_and_extracts(session: Session) -> None:
    owner, project, mat = _ready_material(session)
    out = _run(session, mat)
    assert out["status"] == "READY"
    assert out["embedded"] == 3 and out["concepts_created"] >= 1
    session.expire_all()

    chunks = (
        session.query(DocumentChunk)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(Document.material_id == mat.id)
        .all()
    )
    assert len(chunks) == 3
    assert all(c.embedding is not None and len(c.embedding) == 768 for c in chunks)

    concepts = session.query(Concept).filter_by(project_id=project.id).all()
    assert concepts, "keyword extractor must derive concepts from real content"
    for concept in concepts:
        materials = concept.concept_metadata["materials"]
        assert len(materials) == 1 and materials[0]["material_id"] == str(mat.id)
        assert materials[0]["pages"] == [1]

    job = _job(session, mat)
    assert job.status == JobStatus.SUCCEEDED
    assert job.job_type == KNOWLEDGE_JOB_TYPE

    mat = session.get(Material, mat.id)
    assert mat.status == MaterialStatus.READY  # document state untouched

    assert _events(session, mat, EventType.EMBEDDING_STARTED) == 1
    assert _events(session, mat, EventType.EMBEDDING_COMPLETED) == 1
    assert _events(session, mat, EventType.CONCEPTS_EXTRACTED) == 1


def test_partial_resume_embeds_only_missing(session: Session) -> None:
    owner, project, mat = _ready_material(session)
    out = _run(session, mat)
    assert out["embedded"] == 3

    # Simulate a crash mid-flight: vectors wiped, job left RUNNING but stale.
    session.execute(sa.update(DocumentChunk).values(embedding=None))
    job = _job(session, mat)
    job.status = JobStatus.RUNNING
    job.started_at = utcnow() - timedelta(minutes=60)
    session.commit()

    chunks = ChunkRepository(session).list_unembedded(
        session.query(Document).filter_by(material_id=mat.id).one().id, project.id
    )
    assert len(chunks) == 3
    out = _run(session, mat)  # stale lease reclaimed, missing chunk re-embedded
    assert out["status"] == "READY" and out["embedded"] == 3


def test_duplicate_delivery_is_safe(session: Session) -> None:
    owner, project, mat = _ready_material(session)
    first = _run(session, mat)
    assert first["status"] == "READY"
    second = _run(session, mat)
    assert second["status"] == "already-done"
    assert _events(session, mat, EventType.EMBEDDING_COMPLETED) == 1
    assert session.query(Concept).filter_by(project_id=project.id).count() >= 1
    # No duplicate concepts on rerun.
    before = session.query(Concept).filter_by(project_id=project.id).count()
    _run(session, mat)
    assert session.query(Concept).filter_by(project_id=project.id).count() == before


def test_not_ready_and_missing_skip(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    from app.repositories.materials import MaterialRepository

    mat = MaterialRepository(session).create(project_id=project.id, name="Q")
    session.commit()  # still QUEUED
    out = _run(session, mat)
    assert out == {"status": "skipped", "reason": "not-ready"}
    out = execute_knowledge_processing(
        uuid.uuid4(), session=session, settings=_fake_settings(), ai_service=FakeAI()
    )
    assert out == {"status": "skipped", "reason": "material-missing"}


# ------------------------------------------------------------- claims


def test_claim_loss_and_stale_reclaim(session: Session) -> None:
    from datetime import timedelta

    from app.services.knowledge_service import KnowledgeService

    owner, project, mat = _ready_material(session)
    svc = KnowledgeService(session)
    job = svc.ensure_knowledge_job(project_id=project.id, material_id=mat.id)
    job.status = JobStatus.RUNNING
    job.started_at = utcnow()
    session.commit()

    out = _run(session, mat)
    assert out == {"status": "skipped", "reason": "already-claimed"}
    session.expire_all()
    assert session.get(Material, mat.id).status == MaterialStatus.READY

    job = _job(session, mat)
    job.started_at = utcnow() - timedelta(minutes=60)
    session.commit()
    out = _run(session, mat)  # stale lease reclaimed
    assert out["status"] == "READY"


# ------------------------------------------------------------- failures


def test_transient_embed_failure_retries(session: Session) -> None:
    attempts = {"n": 0}
    inner = DeterministicEmbeddingProvider(dimensions=768)

    class Flaky:
        name = "flaky"

        async def embed(self, request):  # type: ignore[no-untyped-def]
            # Fail more times than the embedding service budget (1 + 3
            # retries) so the failure escapes to the job layer exactly once.
            attempts["n"] += 1
            if attempts["n"] <= 4:
                raise EmbeddingProviderUnavailable("blip")
            return await inner.embed(request)

    class FlakyAI(FakeAI):
        def __init__(self) -> None:
            super().__init__(provider=Flaky())

    owner, project, mat = _ready_material(session)
    with pytest.raises(NeedsRetry):
        _run(session, mat, ai=FlakyAI())
    session.expire_all()
    assert _job(session, mat).status == JobStatus.RETRYING
    out = _run(session, mat, ai=FlakyAI())  # shared counter now passes
    assert out["status"] == "READY"
    assert out["embedded"] == 3


def test_permanent_embed_failure_fails_job(session: Session) -> None:
    class BadKey:
        name = "badkey"

        async def embed(self, request):  # type: ignore[no-untyped-def]
            raise EmbeddingConfigurationError("bad key")

    class BadAI(FakeAI):
        def __init__(self) -> None:
            super().__init__(provider=BadKey())

    owner, project, mat = _ready_material(session)
    out = _run(session, mat, ai=BadAI())
    assert out["status"] == "FAILED"
    session.expire_all()
    refreshed = session.get(Material, mat.id)
    assert refreshed is not None and refreshed.status == MaterialStatus.READY  # untouched
    job = _job(session, mat)
    assert job.status == JobStatus.FAILED and job.error
    assert _events(session, mat, EventType.EMBEDDING_FAILED) == 1
    # Embeddings were never written.
    total, embedded = (
        __import__("app.repositories.materials", fromlist=["ChunkRepository"])
        .ChunkRepository(session)
        .count_embedded_for_material(mat.id)
    )
    assert (total, embedded) == (3, 0)


def test_concept_failure_keeps_embeddings(session: Session) -> None:
    class BadExtractor:
        name = "badex"

        async def extract(self, source_text: str, *, max_concepts: int):  # type: ignore[no-untyped-def]
            raise ConceptExtractionFailed("model gibberish")

    class BadConceptAI(FakeAI):
        def __init__(self) -> None:
            super().__init__(extractor=BadExtractor())

    owner, project, mat = _ready_material(session)
    out = _run(session, mat, ai=BadConceptAI())
    assert out["status"] == "FAILED"
    session.expire_all()
    total, embedded = ChunkRepository(session).count_embedded_for_material(mat.id)
    assert (total, embedded) == (3, 3)  # embeddings durable despite concept failure
    # Retry after explicit reset (what reprocess does): resumes past embeddings.
    job = _job(session, mat)
    job.status = JobStatus.QUEUED
    session.commit()
    out = _run(session, mat)
    assert out["status"] == "READY"


def test_exhaustion_fails_without_infinite_retry(session: Session) -> None:
    class AlwaysDown:
        name = "down"

        async def embed(self, request):  # type: ignore[no-untyped-def]
            raise EmbeddingProviderUnavailable("down")

    class DownAI(FakeAI):
        def __init__(self) -> None:
            super().__init__(provider=AlwaysDown())

    owner, project, mat = _ready_material(session)
    # Force zero budget: create the job row first via ensure, then set max_retries=0.
    from app.services.knowledge_service import KnowledgeService

    svc = KnowledgeService(session)
    job = svc.ensure_knowledge_job(project_id=project.id, material_id=mat.id)
    job.max_retries = 0
    session.commit()
    out = _run(session, mat, ai=DownAI())
    assert out["status"] == "FAILED"
    assert "several attempts" in out["error"]


# ------------------------------------------------------------- chaining


def test_knowledge_task_registered() -> None:
    import app.jobs.document_tasks  # noqa: F401 (registers process_material)
    from app.jobs.celery_app import celery_app

    assert "app.jobs.process_knowledge" in celery_app.tasks
    assert "app.jobs.process_material" in celery_app.tasks


def test_chain_creates_job_and_dispatches(session: Session, monkeypatch) -> None:
    import app.jobs.document_tasks as dt

    seen: list[str] = []

    def _record(mid: uuid.UUID) -> bool:
        seen.append(str(mid))
        return True

    monkeypatch.setattr(dt, "dispatch_knowledge", _record)
    owner, project, mat = _ready_material(session)
    dt._chain_knowledge(session, _fake_settings(), mat.id)
    assert seen == [str(mat.id)]
    job = _job(session, mat)
    assert job.job_type == KNOWLEDGE_JOB_TYPE and job.status == JobStatus.QUEUED
