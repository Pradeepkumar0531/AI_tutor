"""OCR engines: real Tesseract fallback, lazy Paddle→Tesseract chain, failure
taxonomy. These tests execute the actual ``tesseract`` binary (skipped when
absent) — OCR is verified, never faked."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.documents import ocr as ocr_module
from app.documents.errors import OcrFailed, OcrUnavailable, PermanentFailure
from app.documents.ocr import (
    LazyOcrProvider,
    TesseractOcrProvider,
    ocr_status,
    tesseract_available,
)
from app.documents.pipeline import PipelineConfig, process_pdf
from app.jobs.document_tasks import execute_material_processing
from app.models.enums import ExtractionMethod, MaterialStatus
from app.models.materials import Material
from app.storage import LocalStorage, StorageService
from tests.conftest import make_project, make_user
from tests.pdf_fixtures import LOREM, make_scanned_pdf, make_text_pdf

TEXT = LOREM + " Scanned words about photosynthesis and mitochondria."
needs_tesseract = pytest.mark.skipif(
    not tesseract_available(), reason="tesseract binary not on PATH"
)


@pytest.fixture()
def storage(tmp_path):
    return StorageService(LocalStorage(root=str(tmp_path / "storage")), provider="local")


def _material(session: Session, storage: StorageService, data: bytes) -> Material:
    from app.repositories.materials import MaterialRepository, ProcessingJobRepository

    owner = make_user(session)
    project = make_project(session, owner)
    mat = MaterialRepository(session).create(
        project_id=project.id,
        name="Scanned doc",
        original_filename="scan.pdf",
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


class _NoPaddle:
    """Force the paddle-missing branch deterministically in any environment."""

    def __init__(self, *, lang: str = "en") -> None:
        raise OcrUnavailable("paddleocr missing (test)", detail="forced absent")


@needs_tesseract
def test_tesseract_recovers_scanned_pdf() -> None:
    scanned = make_scanned_pdf([TEXT])
    res = process_pdf(scanned, PipelineConfig(), TesseractOcrProvider())
    assert res.ocr_page_count == 1
    assert res.extraction_method == ExtractionMethod.OCR
    body = " ".join(c.content for c in res.chunks)
    for word in ("Photosynthesis", "mitochondria", "retention"):
        assert word.lower() in body.lower()


@needs_tesseract
def test_lazy_chain_falls_back_to_tesseract(monkeypatch) -> None:
    monkeypatch.setattr(ocr_module, "PaddleOcrProvider", _NoPaddle)
    scanned = make_scanned_pdf([TEXT])
    res = process_pdf(scanned, PipelineConfig(), LazyOcrProvider())
    assert res.ocr_page_count == 1
    assert res.extraction_method == ExtractionMethod.OCR


@needs_tesseract
def test_text_pdf_never_invokes_ocr() -> None:
    calls: list[int] = []
    provider = TesseractOcrProvider()
    orig = provider.ocr_page

    def counting(image_png: bytes, *, page_number: int) -> str:
        calls.append(page_number)
        return orig(image_png, page_number=page_number)

    provider.ocr_page = counting  # type: ignore[method-assign]
    res = process_pdf(make_text_pdf([TEXT]), PipelineConfig(), provider)
    assert calls == []
    assert res.extraction_method == ExtractionMethod.TEXT


def test_tesseract_missing_binary_is_unavailable(monkeypatch) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda *args, **kwargs: None)
    with pytest.raises(OcrUnavailable, match="[Oo][Cc][Rr]"):
        TesseractOcrProvider()


def test_ocr_failed_is_permanent_not_retried() -> None:
    """OcrFailed must surface as a loud permanent failure (FAILED state, no
    infinite worker retry) — matching the task's Transient/Permanent split."""

    class _Broken:
        def ocr_page(self, image_png: bytes, *, page_number: int) -> str:
            raise OcrFailed("OCR failed on a scanned page.", detail="forced broken")

    assert issubclass(OcrFailed, PermanentFailure)
    with pytest.raises(OcrFailed):
        process_pdf(make_scanned_pdf([TEXT]), PipelineConfig(), _Broken())


def test_ocr_status_reports_honestly() -> None:
    status = ocr_status()
    assert status["tesseract"] == tesseract_available()
    assert isinstance(status["paddleocr"], bool)


@needs_tesseract
def test_worker_scanned_pdf_goes_ready(monkeypatch, session: Session, storage) -> None:
    """Full worker path: scanned upload → PROCESSING → READY with OCR text,
    knowledge chained (same as the text path, no special-casing)."""
    monkeypatch.setattr(ocr_module, "PaddleOcrProvider", _NoPaddle)
    mat = _material(session, storage, make_scanned_pdf([TEXT, TEXT]))
    out = execute_material_processing(
        mat.id,
        session=session,
        settings=get_settings(),
        storage=storage,
        ocr_provider_factory=LazyOcrProvider,
    )
    assert out["status"] == "READY"
    assert out["ocr_pages"] == 2
    session.expire_all()
    assert session.get(Material, mat.id).status == MaterialStatus.READY


@needs_tesseract
def test_worker_scanned_pdf_retry_after_transient(monkeypatch, session: Session, storage) -> None:
    """Worker restart safety: a retry re-runs the same OCR path idempotently."""
    from app.jobs.retry import NeedsRetry

    monkeypatch.setattr(ocr_module, "PaddleOcrProvider", _NoPaddle)
    mat = _material(session, storage, make_scanned_pdf([TEXT]))
    attempts = {"n": 0}

    def flaky_factory():
        class _Flaky(LazyOcrProvider):
            def ocr_page(self, image_png: bytes, *, page_number: int) -> str:
                attempts["n"] += 1
                if attempts["n"] == 1:
                    raise OSError("simulated IO blip")
                return super().ocr_page(image_png, page_number=page_number)

        return _Flaky()

    from app.jobs.document_tasks import execute_material_processing as run

    with pytest.raises(NeedsRetry):
        run(mat.id, session=session, settings=get_settings(), storage=storage,
            ocr_provider_factory=flaky_factory)
    out = run(mat.id, session=session, settings=get_settings(), storage=storage,
              ocr_provider_factory=LazyOcrProvider)
    assert out["status"] == "READY"
    assert out["ocr_pages"] == 1
