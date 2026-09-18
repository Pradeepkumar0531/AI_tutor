"""OCR fallback boundary. OCR engines stay *optional* dependencies: the pipeline
depends on this protocol, never on an OCR package. When text extraction is
insufficient for a page and no OCR engine is available, processing fails
loudly — never a silent READY with missing content.

Engine chain (first available wins, resolved lazily on first use so
text-only documents never pay import cost):
1. PaddleOCR (``pip install -e ".[ocr]"`` — heavy, best accuracy), then
2. Tesseract via the ``tesseract`` CLI (light; present on most images)."""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Protocol

from app.documents.errors import OcrFailed, OcrUnavailable

log = logging.getLogger("app.documents")

#: Hard ceiling per page so one pathological scan can never wedge a worker
#: past the Celery task time limit (30 min for the whole document).
TESSERACT_TIMEOUT_S = 300

_TESSERACT_LANGS = {
    "en": "eng",
    "de": "deu",
    "fr": "fra",
    "es": "spa",
    "it": "ita",
    "pt": "por",
    "nl": "nld",
}


class OcrProvider(Protocol):
    def ocr_page(self, image_png: bytes, *, page_number: int) -> str: ...


class PaddleOcrProvider:
    """PaddleOCR-backed provider. Import is lazy so the API/worker boot without
    the heavy optional dependency; absence surfaces as OcrUnavailable."""

    def __init__(self, *, lang: str = "en") -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise OcrUnavailable(
                "OCR is required for this document but is not installed.",
                detail=f"paddleocr missing: {e}",
            ) from e
        # show_log=False keeps worker logs clean; use_gpu=False is portable.
        self._ocr = PaddleOCR(lang=lang, show_log=False, use_gpu=False)

    def ocr_page(self, image_png: bytes, *, page_number: int) -> str:
        import tempfile
        from pathlib import Path

        # PaddleOCR reads from disk; use a scoped temp file, never the repo.
        with tempfile.TemporaryDirectory(prefix="alc-ocr-") as tmp:
            img_path = Path(tmp) / f"page-{page_number}.png"
            img_path.write_bytes(image_png)
            try:
                result = self._ocr.ocr(str(img_path))
            except Exception as e:
                raise OcrFailed(
                    "OCR failed on a scanned page.",
                    detail=f"page={page_number} err={type(e).__name__}: {e}",
                ) from e
        lines: list[str] = []
        for page_result in result or []:
            for line in page_result or []:
                try:
                    text = line[1][0]
                except (IndexError, TypeError):
                    continue
                if text:
                    lines.append(str(text))
        return "\n".join(lines)


class NullOcrProvider:
    """Test/CI stand-in that behaves like 'OCR not installed'."""

    def ocr_page(self, image_png: bytes, *, page_number: int) -> str:
        raise OcrUnavailable(
            "OCR is required for this document but is not installed.",
            detail="NullOcrProvider always unavailable",
        )


class TesseractOcrProvider:
    """Tesseract CLI-backed provider. No Python dependency: shells out to the
    ``tesseract`` binary (stdin PNG → stdout text). Raises OcrUnavailable at
    construction when the binary is absent; per-page failures (timeout,
    non-zero exit, empty output on a page that needs text) raise OcrFailed."""

    def __init__(self, *, lang: str = "en") -> None:
        binary = shutil.which("tesseract")
        if binary is None:
            raise OcrUnavailable(
                "OCR is required for this document but is not installed.",
                detail="tesseract binary not found on PATH",
            )
        self._binary = binary
        self._lang = _TESSERACT_LANGS.get(lang, "eng")

    def ocr_page(self, image_png: bytes, *, page_number: int) -> str:
        try:
            proc = subprocess.run(
                [self._binary, "stdin", "stdout", "--psm", "6", "-l", self._lang],
                input=image_png,
                capture_output=True,
                timeout=TESSERACT_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as e:
            raise OcrFailed(
                "OCR timed out on a scanned page.",
                detail=f"page={page_number} timeout_s={TESSERACT_TIMEOUT_S}",
            ) from e
        except OSError as e:
            raise OcrFailed(
                "OCR failed on a scanned page.",
                detail=f"page={page_number} err={type(e).__name__}: {e}",
            ) from e
        if proc.returncode != 0:
            raise OcrFailed(
                "OCR failed on a scanned page.",
                detail=f"page={page_number} rc={proc.returncode} "
                f"stderr={proc.stderr.decode('utf-8', 'replace')[:300]}",
            )
        return proc.stdout.decode("utf-8", "replace")


def paddle_available() -> bool:
    try:
        import paddleocr  # noqa: F401
    except ImportError:
        return False
    return True


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def ocr_status() -> dict:
    """Honest capability report for logs/health checks (never faked)."""
    return {"paddleocr": paddle_available(), "tesseract": tesseract_available()}


class LazyOcrProvider:
    """Defers engine construction until the first page that needs it, trying
    PaddleOCR first and falling back to Tesseract when PaddleOCR is not
    installed. Used by the worker so text-only documents never pay import
    cost and never fail for a missing optional dependency they do not need."""

    def __init__(self, *, lang: str = "en") -> None:
        self._lang = lang
        self._inner: OcrProvider | None = None

    def ocr_page(self, image_png: bytes, *, page_number: int) -> str:
        if self._inner is None:
            try:
                self._inner = PaddleOcrProvider(lang=self._lang)
                log.info("ocr engine selected: paddleocr")
            except OcrUnavailable:
                log.info("paddleocr unavailable, falling back to tesseract")
                self._inner = TesseractOcrProvider(lang=self._lang)
        return self._inner.ocr_page(image_png, page_number=page_number)


def build_ocr_provider(*, enabled: bool, lang: str = "en") -> OcrProvider | None:
    """Return a provider when OCR may be needed, else None (OCR disabled)."""
    if not enabled:
        return None
    return LazyOcrProvider(lang=lang)
