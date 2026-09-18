"""Document processing package: validation, extraction, OCR, normalize, chunk.

Public surface re-exported here; stage modules hold the implementations.
HTTP must never run the full pipeline synchronously — see ``pipeline.py``
(docstring) and the ``process_material`` Celery task in ``app.jobs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.documents.chunking import ChunkConfig, PageInput, TextChunk, chunk_pages
from app.documents.errors import (
    DocumentTooLarge,
    ExtractionFailed,
    NoUsableContent,
    OcrFailed,
    OcrUnavailable,
    PermanentFailure,
    TransientFailure,
)
from app.documents.normalize import normalize_text
from app.documents.ocr import (
    LazyOcrProvider,
    NullOcrProvider,
    OcrProvider,
    TesseractOcrProvider,
    build_ocr_provider,
    ocr_status,
    paddle_available,
    tesseract_available,
)
from app.documents.pipeline import PipelineConfig, PipelineResult, process_pdf
from app.documents.validation import (
    UploadTooLargeError,
    UploadValidationError,
    ValidatedUpload,
    build_storage_key,
    validate_pdf_upload,
)

__all__ = [
    "ChunkConfig",
    "DocumentMetadata",
    "DocumentStatus",
    "DocumentTooLarge",
    "ExtractionFailed",
    "NoUsableContent",
    "LazyOcrProvider",
    "NullOcrProvider",
    "OcrFailed",
    "OcrProvider",
    "OcrUnavailable",
    "PageInput",
    "PermanentFailure",
    "PipelineConfig",
    "PipelineResult",
    "TesseractOcrProvider",
    "TextChunk",
    "TransientFailure",
    "UploadTooLargeError",
    "UploadValidationError",
    "ValidatedUpload",
    "build_ocr_provider",
    "build_storage_key",
    "chunk_pages",
    "normalize_text",
    "ocr_status",
    "paddle_available",
    "process_pdf",
    "tesseract_available",
    "validate_pdf_upload",
]


class DocumentStatus(StrEnum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass
class DocumentMetadata:
    filename: str
    mime_type: str
    size_bytes: int
    extra: dict = field(default_factory=dict)
