"""Document processing pipeline: bytes in, Document fields + chunks + images out.

Pure orchestration over ``extract``/``normalize``/``ocr``/``chunking``/``images``
— no database, no storage, no Celery here, so tests execute the exact
production logic deterministically. The Celery task in ``app.jobs`` handles
claiming, persistence, events, and retries around this function.

Flow per page: extract -> normalize -> (OCR fallback when below threshold) ->
page inputs -> deterministic page-aware chunking, plus embedded-raster image
extraction with deterministic filtering. Empty/low-content documents raise
NoUsableContent; embeddings stay None (Prompt 6 owns them). Image extraction
is enhancement-only: its failure never fails text processing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.documents import chunking
from app.documents.chunking import ChunkConfig, PageInput, TextChunk
from app.documents.errors import (
    DocumentTooLarge,
    ExtractionFailed,
    NoUsableContent,
    OcrUnavailable,
)
from app.documents.extract import ExtractedDocument, extract_pages, render_page_png
from app.documents.images import RawImage, extract_embedded_images, filter_images
from app.documents.normalize import normalize_text
from app.documents.ocr import OcrProvider
from app.models.enums import ExtractionMethod

log = logging.getLogger("app.documents")


@dataclass(frozen=True)
class PipelineConfig:
    max_pages: int = 500
    max_chars: int = 2_000_000
    chunk_size: int = 1000
    chunk_overlap: int = 150
    min_chunk_chars: int = 100
    ocr_min_chars_per_page: int = 50
    ocr_enabled: bool = True
    ocr_dpi: int = 200
    image_extraction_enabled: bool = True
    min_image_width: int = 100
    min_image_height: int = 100
    min_image_bytes: int = 2048
    max_images_per_page: int = 10
    max_images_per_document: int = 50


@dataclass
class PipelineResult:
    page_count: int
    extraction_method: ExtractionMethod
    title: str | None
    author: str | None
    char_count: int
    ocr_page_count: int
    chunk_count: int
    duration_ms: int
    chunks: list[TextChunk] = field(default_factory=list)
    doc_metadata: dict = field(default_factory=dict)
    images: list[RawImage] = field(default_factory=list)
    image_stats: dict = field(default_factory=dict)


def _needs_ocr(normalized: str, threshold: int) -> bool:
    return len(normalized.strip()) < threshold


def process_pdf(
    data: bytes,
    config: PipelineConfig,
    ocr_provider: OcrProvider | None,
) -> PipelineResult:
    """Run extraction -> normalize -> OCR fallback -> chunking.

    Raises PermanentFailure subclasses (ExtractionFailed, DocumentTooLarge,
    NoUsableContent, OcrUnavailable, ...) on any unprocessable input.
    """
    started = time.perf_counter()
    extracted: ExtractedDocument = extract_pages(data, max_pages=config.max_pages)

    page_inputs: list[PageInput] = []
    ocr_pages = 0
    used_ocr = False
    total_chars = 0

    for page in extracted.pages:
        normalized = normalize_text(page.text)
        method = "text"
        if _needs_ocr(normalized, config.ocr_min_chars_per_page):
            has_text = len(normalized.strip()) > 0
            if not config.ocr_enabled:
                if not has_text:
                    raise NoUsableContent(
                        "The PDF has no readable text on "
                        f"page {page.page_number}, and OCR is disabled.",
                        detail=f"page={page.page_number} chars=0",
                    )
                log.debug("short page kept as text (ocr disabled) page=%s", page.page_number)
            elif ocr_provider is None:
                if not has_text:
                    raise OcrUnavailable(
                        f"The PDF needs OCR on page {page.page_number}, but OCR is not installed.",
                        detail=f"page={page.page_number} chars=0",
                    )
            else:
                try:
                    png = render_page_png(data, page.page_number, dpi=config.ocr_dpi)
                    ocr_text = ocr_provider.ocr_page(png, page_number=page.page_number)
                except OcrUnavailable:
                    if not has_text:
                        raise
                    # Short but real extracted text survives a missing OCR
                    # install; only fully empty pages are fatal.
                    log.warning(
                        "ocr unavailable, keeping short extracted text page=%s",
                        page.page_number,
                    )
                else:
                    ocr_clean = normalize_text(ocr_text)
                    if ocr_clean.strip():
                        normalized = ocr_clean
                        method = "ocr"
                        ocr_pages += 1
                    elif not has_text:
                        log.info("page still empty after OCR page=%s", page.page_number)
        if normalized.strip():
            page_inputs.append(PageInput(page_number=page.page_number, text=normalized))
            total_chars += len(normalized)
            if method == "ocr":
                used_ocr = True
        log.debug(
            "page done page=%s method=%s chars=%s",
            page.page_number,
            method,
            len(normalized.strip()),
        )

    if total_chars == 0:
        raise NoUsableContent(
            "The PDF could not be processed because no readable text was found.",
            detail=f"pages={extracted.page_count} ocr_pages={ocr_pages}",
        )
    if total_chars > config.max_chars:
        raise DocumentTooLarge(
            "This PDF contains more text than can be processed "
            f"({total_chars} characters; limit {config.max_chars}).",
            detail=f"chars={total_chars} max_chars={config.max_chars}",
        )

    chunks = chunking.chunk_pages(
        page_inputs,
        ChunkConfig(
            chunk_size=config.chunk_size,
            overlap=config.chunk_overlap,
            min_chunk_chars=config.min_chunk_chars,
        ),
    )
    if not chunks:
        raise NoUsableContent(
            "The PDF could not be processed because no readable text was found.",
            detail="chunking produced zero chunks",
        )

    if ocr_pages > 0 and used_ocr:
        method_enum = (
            ExtractionMethod.MIXED if ocr_pages < extracted.page_count else ExtractionMethod.OCR
        )
    elif ocr_pages > 0:
        # OCR ran but contributed nothing usable; text extraction did the work.
        method_enum = ExtractionMethod.TEXT
    else:
        method_enum = ExtractionMethod.TEXT

    images, image_stats = _extract_images(data, config)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return PipelineResult(
        page_count=extracted.page_count,
        extraction_method=method_enum,
        title=extracted.title,
        author=extracted.author,
        char_count=total_chars,
        ocr_page_count=ocr_pages,
        chunk_count=len(chunks),
        duration_ms=duration_ms,
        chunks=chunks,
        doc_metadata={
            "title": extracted.title,
            "author": extracted.author,
            "ocr_pages": ocr_pages,
            "extraction": method_enum.value,
            "images_extracted": image_stats.get("extracted", 0),
            "images_kept": image_stats.get("kept", 0),
            "images_filtered": image_stats.get("filtered", 0),
        },
        images=images,
        image_stats=image_stats,
    )


def _extract_images(data: bytes, config: PipelineConfig) -> tuple[list[RawImage], dict]:
    """Embedded-raster pass. Enhancement-only by design: any failure here is
    logged and yields zero images rather than failing text processing."""
    if not config.image_extraction_enabled:
        return [], {"extracted": 0, "kept": 0, "filtered": 0}
    try:
        candidates = extract_embedded_images(data, max_pages=config.max_pages)
    except ExtractionFailed as e:
        log.warning("image extraction skipped err=%s", e.detail)
        return [], {"extracted": 0, "kept": 0, "filtered": 0}
    kept, stats = filter_images(
        candidates,
        min_width=config.min_image_width,
        min_height=config.min_image_height,
        min_bytes=config.min_image_bytes,
        max_per_page=config.max_images_per_page,
        max_per_doc=config.max_images_per_document,
    )
    return kept, stats
