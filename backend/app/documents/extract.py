"""Primary PDF extraction with PyMuPDF. Page boundaries are first-class:
every returned page carries its 1-based number for RAG citations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.documents.errors import DocumentTooLarge, ExtractionFailed

log = logging.getLogger("app.documents")


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based
    text: str
    char_count: int


@dataclass(frozen=True)
class ExtractedDocument:
    pages: list[PageText]
    page_count: int
    title: str | None
    author: str | None


def extract_pages(data: bytes, *, max_pages: int) -> ExtractedDocument:
    """Open + extract text per page. Corrupt/unreadable PDFs raise
    ExtractionFailed (permanent); oversized docs raise DocumentTooLarge."""
    try:
        import pymupdf
    except ImportError as e:  # pragma: no cover - pymupdf is a hard dependency
        raise ExtractionFailed(
            "PDF processing is unavailable.",
            detail=f"pymupdf missing: {e}",
        ) from e
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise ExtractionFailed(
            "The PDF could not be read. It may be corrupt or password-protected.",
            detail=f"pymupdf.open failed: {type(e).__name__}: {e}",
        ) from e
    try:
        if doc.page_count > max_pages:
            raise DocumentTooLarge(
                f"This PDF has {doc.page_count} pages; the limit is {max_pages}.",
                detail=f"page_count={doc.page_count} max_pages={max_pages}",
            )
        meta = doc.metadata or {}
        pages: list[PageText] = []
        for i in range(doc.page_count):
            page = doc[i]
            try:
                text = page.get_text("text") or ""
            except Exception as e:
                log.warning("page text extraction failed page=%s err=%s", i + 1, e)
                text = ""
            pages.append(PageText(page_number=i + 1, text=text, char_count=len(text)))
        return ExtractedDocument(
            pages=pages,
            page_count=doc.page_count,
            title=meta.get("title") or None,
            author=meta.get("author") or None,
        )
    finally:
        doc.close()


def render_page_png(data: bytes, page_number: int, *, dpi: int = 200) -> bytes:
    """Render one 1-based page to PNG bytes for OCR input."""
    try:
        import pymupdf
    except ImportError as e:  # pragma: no cover
        raise ExtractionFailed("PDF processing is unavailable.", detail=str(e)) from e
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:
        raise ExtractionFailed(
            "The PDF could not be read.", detail=f"render open failed: {e}"
        ) from e
    try:
        if not 1 <= page_number <= doc.page_count:
            raise ExtractionFailed(
                "The PDF could not be read.",
                detail=f"page {page_number} out of range (count={doc.page_count})",
            )
        pix = doc[page_number - 1].get_pixmap(dpi=dpi)
        return bytes(pix.tobytes("png"))
    except ExtractionFailed:
        raise
    except Exception as e:
        raise ExtractionFailed("The PDF could not be read.", detail=f"render failed: {e}") from e
    finally:
        doc.close()
