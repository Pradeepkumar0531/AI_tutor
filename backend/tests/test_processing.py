"""Document processing: pipeline units, worker execution paths, OCR, idempotency,
concurrency, retries. The real ``execute_material_processing`` runs against the
shared SQLite session + isolated local storage — same code the worker executes.
"""

from __future__ import annotations

import shutil
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.documents.chunking import ChunkConfig, PageInput, chunk_pages
from app.documents.errors import (
    DocumentTooLarge,
    ExtractionFailed,
    NoUsableContent,
    OcrUnavailable,
    PermanentFailure,
)
from app.documents.normalize import normalize_text
from app.documents.ocr import LazyOcrProvider, NullOcrProvider
from app.documents.pipeline import PipelineConfig, process_pdf
from app.jobs.document_tasks import execute_material_processing
from app.jobs.retry import NeedsRetry as _NeedsRetry
from app.models.enums import EventType, ExtractionMethod, JobStatus, MaterialStatus
from app.models.materials import Document, DocumentChunk, Material
from app.models.ops import Event, ProcessingJob
from app.storage import LocalStorage, StorageService
from tests.conftest import make_project, make_user
from tests.pdf_fixtures import LOREM, make_blank_pdf, make_corrupt_pdf, make_text_pdf

PDF = make_text_pdf([LOREM, LOREM + " Second page."])
LONG = " ".join([f"Sentence number {i} about learning and memory." for i in range(200)])


@pytest.fixture()
def storage(tmp_path):
    return StorageService(LocalStorage(root=str(tmp_path / "storage")), provider="local")


def _material(session: Session, storage: StorageService, data: bytes = PDF) -> Material:
    """Persist a QUEUED material + job row the way upload_material would."""
    from app.repositories.materials import MaterialRepository, ProcessingJobRepository

    owner = make_user(session)
    project = make_project(session, owner)
    mat = MaterialRepository(session).create(
        project_id=project.id,
        name="Doc",
        original_filename="d.pdf",
        mime_type="application/pdf",
        file_size=len(data),
    )
    session.flush()
    key = f"projects/{project.id.hex}/materials/{mat.id.hex}/original.pdf"
    storage.put(key, data, "application/pdf")
    mat.storage_key = key
    ProcessingJobRepository(session).enqueue(
        job_type="document.process",
        project_id=project.id,
        material_id=mat.id,
        idempotency_key=f"material:{mat.id}:process",
        payload={"material_id": str(mat.id)},
    )
    session.commit()
    return mat


def _run(session, storage, mat: Material, **kwargs):
    return execute_material_processing(
        mat.id,
        session=session,
        settings=get_settings(),
        storage=storage,
        ocr_provider_factory=kwargs.get("ocr_factory", NullOcrProvider),
    )


def _job(session: Session, mat: Material) -> ProcessingJob:
    return session.query(ProcessingJob).filter_by(material_id=mat.id).one()


# ------------------------------------------------------------ pipeline units


def test_normalize_preserves_structure() -> None:
    out = normalize_text("Title\r\n\n\nBody   with   spaces\tkept.\n\n\n\nNext para.")
    assert out == "Title\n\nBody with spaces\tkept.\n\nNext para."
    assert normalize_text("a\x00b\x07c") == "abc"
    assert normalize_text("") == ""


def test_chunking_is_deterministic_page_aware() -> None:
    pages = [
        PageInput(
            page_number=1,
            text="Para one is here now.\n\nPara two is here now.\n\nPara three here now.",
        ),
        PageInput(page_number=2, text="Page two paragraph."),
    ]
    cfg = ChunkConfig(chunk_size=60, overlap=10, min_chunk_chars=10)
    first = [(c.content, c.page_start, c.page_end) for c in chunk_pages(pages, cfg)]
    second = [(c.content, c.page_start, c.page_end) for c in chunk_pages(pages, cfg)]
    assert first == second  # deterministic
    assert all(s == e for _, s, e in first)  # never spans pages
    assert [s for _, s, _ in first] == [1, 1, 2]
    assert [c for c, _, _ in first if c]  # no empty chunks


def test_chunking_merges_dust_and_splits_giants() -> None:
    pages = [PageInput(page_number=1, text="Tiny.\n\n" + "x" * 2000)]
    chunks = chunk_pages(pages, ChunkConfig(chunk_size=500, overlap=50, min_chunk_chars=100))
    assert len(chunks) >= 4
    assert all(len(c.content) <= 500 + 50 + 2 for c in chunks)


def test_process_pdf_text_path() -> None:
    res = process_pdf(PDF, PipelineConfig(), NullOcrProvider())
    assert res.page_count == 2
    assert res.extraction_method == ExtractionMethod.TEXT
    assert res.ocr_page_count == 0 and res.chunk_count == 2
    assert res.chunks[0].page_start == 1 and res.chunks[1].page_start == 2


def test_process_pdf_rejects_blank_and_corrupt() -> None:
    # Blank with OCR disabled: genuinely no usable content.
    with pytest.raises(NoUsableContent, match="no readable text"):
        process_pdf(make_blank_pdf(), PipelineConfig(ocr_enabled=False), NullOcrProvider())
    # Blank with OCR enabled but unavailable: loud, actionable failure.
    with pytest.raises(OcrUnavailable):
        process_pdf(make_blank_pdf(), PipelineConfig(), NullOcrProvider())
    with pytest.raises(PermanentFailure):
        process_pdf(make_corrupt_pdf(), PipelineConfig(), NullOcrProvider())
    with pytest.raises(ExtractionFailed):
        process_pdf(b"%PDF-1.4\ntrailing garbage, no objects", PipelineConfig(), NullOcrProvider())


def test_process_pdf_enforces_page_limit() -> None:
    big = make_text_pdf([LOREM] * 5)
    with pytest.raises(DocumentTooLarge):
        process_pdf(big, PipelineConfig(max_pages=2), NullOcrProvider())


# ------------------------------------------------------------ OCR


class FakeOcr:
    """Deterministic stand-in behind the OcrProvider protocol."""

    def __init__(self, text: str = "Scanned words recovered by OCR.") -> None:
        self.text = text
        self.calls: list[int] = []

    def ocr_page(self, image_png: bytes, *, page_number: int) -> str:
        assert image_png[:8] == b"\x89PNG\r\n\x1a\n"  # real rendered PNG in
        self.calls.append(page_number)
        return self.text


def test_ocr_fallback_recovers_scanned_pages() -> None:
    fake = FakeOcr()
    res = process_pdf(make_blank_pdf(), PipelineConfig(), fake)
    assert (
        res.extraction_method == ExtractionMethod.MIXED
        or res.extraction_method == ExtractionMethod.OCR
    )
    assert res.ocr_page_count == 1
    assert fake.calls == [1]
    assert res.chunks[0].page_start == 1
    assert "Scanned words" in res.chunks[0].content


def test_short_page_survives_without_ocr() -> None:
    """A page with little (but real) text must not fail for missing OCR —
    only fully empty pages are fatal."""
    res = process_pdf(make_text_pdf(["A short page."]), PipelineConfig(), NullOcrProvider())
    assert res.extraction_method == ExtractionMethod.TEXT
    assert res.ocr_page_count == 0
    assert res.chunks[0].page_start == 1


def test_ocr_unavailable_fails_loudly(monkeypatch) -> None:
    with pytest.raises(OcrUnavailable, match="[Oo][Cc][Rr]"):
        process_pdf(make_blank_pdf(), PipelineConfig(), NullOcrProvider())
    # Lazy provider with *no* engine installed defers the missing-dependency
    # error until actually needed (both engines forced absent so this holds
    # in every environment, with or without the optional OCR extra / binary).
    from app.documents import ocr as ocr_module
    from app.documents.errors import OcrUnavailable as _OcrUnavailable

    class _MissingPaddle:
        def __init__(self, *, lang: str = "en") -> None:
            raise _OcrUnavailable("paddleocr missing (test)", detail="forced absent")

    monkeypatch.setattr(ocr_module, "PaddleOcrProvider", _MissingPaddle)
    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: None)
    lazy = LazyOcrProvider()
    with pytest.raises(OcrUnavailable):
        lazy.ocr_page(b"fake-png", page_number=1)
    # ...but a text PDF never touches OCR at all.
    res = process_pdf(PDF, PipelineConfig(), lazy)
    assert res.extraction_method == ExtractionMethod.TEXT


def test_ocr_disabled_is_explicit() -> None:
    with pytest.raises(NoUsableContent):
        process_pdf(make_blank_pdf(), PipelineConfig(ocr_enabled=False), FakeOcr())


# ------------------------------------------------------------ worker execution


def test_happy_path_ready(session: Session, storage: StorageService) -> None:
    mat = _material(session, storage)
    out = _run(session, storage, mat)
    assert out["status"] == "READY"
    assert out["pages"] == 2 and out["chunks"] == 2 and out["ocr_pages"] == 0

    session.expire_all()
    mat = session.get(Material, mat.id)
    assert mat.status == MaterialStatus.READY
    assert mat.processing_error is None
    assert mat.processing_completed_at is not None

    doc = session.query(Document).filter_by(material_id=mat.id).one()
    assert doc.page_count == 2 and doc.extraction_method == ExtractionMethod.TEXT
    assert doc.doc_metadata["chunk_count"] == 2
    chunks = (
        session.query(DocumentChunk)
        .filter_by(document_id=doc.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    assert [c.page_start for c in chunks] == [1, 2]
    assert all(c.embedding is None for c in chunks)  # Prompt 6 owns embeddings
    assert all(c.project_id == mat.project_id for c in chunks)

    job = _job(session, mat)
    assert job.status == JobStatus.SUCCEEDED and job.error is None

    types = [
        e.event_type
        for e in session.query(Event)
        .filter(Event.entity_id == mat.id)
        .order_by(Event.created_at)
        .all()
    ]
    assert EventType.MATERIAL_PROCESSING_STARTED in types
    assert EventType.MATERIAL_READY in types


def test_blank_pdf_fails_with_safe_message(session: Session, storage: StorageService) -> None:
    # No OCR in this environment: the honest failure names the missing capability.
    mat = _material(session, storage, make_blank_pdf())
    out = _run(session, storage, mat)
    assert out["status"] == "FAILED"
    assert "OCR" in out["error"]
    session.expire_all()
    mat = session.get(Material, mat.id)
    assert mat.status == MaterialStatus.FAILED
    assert "OCR" in (mat.processing_error or "")
    assert session.query(Document).filter_by(material_id=mat.id).count() == 0
    job = _job(session, mat)
    assert job.status == JobStatus.FAILED and job.error
    failed = (
        session.query(Event)
        .filter(Event.entity_id == mat.id, Event.event_type == EventType.MATERIAL_FAILED)
        .all()
    )
    assert len(failed) == 1


def test_missing_storage_object_fails_permanently(
    session: Session, storage: StorageService
) -> None:
    mat = _material(session, storage)
    mat.storage_key = "projects/does/not-exist.pdf"
    session.commit()
    out = _run(session, storage, mat)
    assert out["status"] == "FAILED"
    assert "re-upload" in out["error"]


def test_missing_material_is_safe_noop(session: Session, storage: StorageService) -> None:
    out = execute_material_processing(
        uuid.uuid4(),
        session=session,
        settings=get_settings(),
        storage=storage,
        ocr_provider_factory=NullOcrProvider,
    )
    assert out == {"status": "skipped", "reason": "material-missing"}


def test_idempotent_rerun_no_duplicates(session: Session, storage: StorageService) -> None:
    mat = _material(session, storage)
    first = _run(session, storage, mat)
    assert first["status"] == "READY"
    second = _run(session, storage, mat)
    assert second["status"] == "already-done"
    assert session.query(Document).filter_by(material_id=mat.id).count() == 1
    assert (
        session.query(DocumentChunk)
        .join(Document, DocumentChunk.document_id == Document.id)
        .filter(Document.material_id == mat.id)
        .count()
        == first["chunks"]
    )
    ready_events = (
        session.query(Event)
        .filter(Event.entity_id == mat.id, Event.event_type == EventType.MATERIAL_READY)
        .all()
    )
    assert len(ready_events) == 1  # no duplicate READY event


def test_deterministic_chunks_across_materials(session: Session, storage: StorageService) -> None:
    mat1 = _material(session, storage)
    mat2 = _material(session, storage)
    _run(session, storage, mat1)
    _run(session, storage, mat2)

    def contents(m):
        return [
            (c.chunk_index, c.content, c.page_start, c.page_end)
            for c in session.query(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(Document.material_id == m.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        ]

    assert contents(mat1) == contents(mat2)


def test_concurrent_claim_loses_gracefully(session: Session, storage: StorageService) -> None:
    from datetime import timedelta

    from app.models.mixins import utcnow

    mat = _material(session, storage)
    job = _job(session, mat)
    job.status = JobStatus.RUNNING  # another worker owns it right now
    job.started_at = utcnow()
    session.commit()
    out = _run(session, storage, mat)
    assert out == {"status": "skipped", "reason": "already-claimed"}
    session.expire_all()
    assert session.get(Material, mat.id).status == MaterialStatus.QUEUED

    # ...but a stale RUNNING claim (crashed worker) may be reclaimed.
    job = _job(session, mat)
    job.started_at = utcnow() - timedelta(minutes=60)
    session.commit()
    out = _run(session, storage, mat)
    assert out["status"] == "READY"


def test_transient_failure_retries_then_succeeds(session: Session, storage: StorageService) -> None:
    from app.storage import StorageError as SE

    mat = _material(session, storage)
    real_get = storage.get
    calls = {"n": 0}

    def flaky(key):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SE("simulated network blip")
        return real_get(key)

    orig = storage.get
    storage.get = flaky  # type: ignore[method-assign]
    try:
        with pytest.raises(_NeedsRetry) as excinfo:
            _run(session, storage, mat)
        assert excinfo.value.countdown > 0
        session.expire_all()
        assert _job(session, mat).status == JobStatus.RETRYING
        out = _run(session, storage, mat)  # retry succeeds through the same stub
        assert out["status"] == "READY"
        assert calls["n"] == 2
    finally:
        storage.get = orig  # type: ignore[method-assign]


def test_transient_failure_exhausts_to_failed(session: Session, storage: StorageService) -> None:
    from app.storage import StorageError as SE

    mat = _material(session, storage)
    job = _job(session, mat)
    job.max_retries = 0  # attempt (1) already exceeds budget
    session.commit()

    def always_down(key):
        raise SE("storage is down")

    storage.get = always_down  # type: ignore[method-assign]
    out = execute_material_processing(
        mat.id,
        session=session,
        settings=get_settings(),
        storage=storage,
        ocr_provider_factory=NullOcrProvider,
    )
    assert out["status"] == "FAILED"
    assert "several attempts" in out["error"]
    session.expire_all()
    assert session.get(Material, mat.id).status == MaterialStatus.FAILED


# ------------------------------------------------------------ dispatch + discovery


def test_task_registered_and_ping_alive() -> None:
    from app.jobs.celery_app import celery_app

    assert "app.jobs.process_material" in celery_app.tasks
    assert "app.jobs.ping" in celery_app.tasks


def test_dispatch_contract(monkeypatch) -> None:
    from kombu.exceptions import OperationalError

    import app.jobs.dispatch as dispatch
    from app.jobs import document_tasks

    seen: list[str] = []
    monkeypatch.setattr(
        document_tasks.process_material,
        "delay",
        lambda mid: seen.append(mid) or object(),
    )
    assert dispatch.dispatch_processing(uuid.uuid4()) is True
    assert len(seen) == 1

    def down(_mid):
        raise OperationalError("broker down")

    monkeypatch.setattr(document_tasks.process_material, "delay", down)
    assert dispatch.dispatch_processing(uuid.uuid4()) is False
