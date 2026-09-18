"""Embedded raster image extraction with PyMuPDF + deterministic filtering.

Only embedded raster images are handled (no page screenshots, no vector
objects): for each page, ``page.get_images(full=True)`` xrefs are resolved
via ``doc.extract_image`` to original bytes. Alpha masks are skipped (they
are not viewable images), as are uncommon/unsupported encodings.

Filtering rationale (centralized thresholds, no magic numbers): educational
PDFs are full of logos, icons, bullets, tracking pixels, and repeated
headers/footers. Anything under 100px on a side or 2KB is decor, not content;
per-page/per-document caps bound worker memory and time. Caps keep the FIRST
images in document order (deterministic); the rest count as filtered.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

from app.documents.errors import DocumentTooLarge, ExtractionFailed

log = logging.getLogger("app.documents")

# Original encodings we store as-is (browsers render all of these; the bytes
# are preserved verbatim, never re-encoded). Anything else (jpx, jbig2,
# ccitt, …) is skipped and counted as filtered — documented limitation.
_ALLOWED_EXTENSIONS = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
}


@dataclass(frozen=True)
class RawImage:
    """One kept embedded-raster occurrence. ``image_index`` is the page-local
    sequence over extracted candidates (gaps possible where filtering dropped
    entries); ``data`` holds the original encoded bytes."""

    page_number: int  # 1-based, matches chunk page provenance
    image_index: int
    width: int
    height: int
    mime_type: str
    ext: str
    sha256: str
    size_bytes: int
    data: bytes


def build_image_storage_key(
    *, project_id: uuid.UUID, material_id: uuid.UUID, sha256: str, ext: str
) -> str:
    """Content-addressed server-side key: identical binaries share one object
    (idempotent puts), scoped to the material. UUIDs + hash only."""
    return f"projects/{project_id.hex}/materials/{material_id.hex}/images/{sha256}.{ext}"


def extract_embedded_images(data: bytes, *, max_pages: int) -> list[RawImage]:
    """Extract kept-candidate embedded rasters from every page. Per-image
    failures are logged and skipped (one bad image never fails a document);
    only a wholly unreadable document raises."""
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
        images: list[RawImage] = []
        for page_number_1 in range(1, doc.page_count + 1):
            page = doc[page_number_1 - 1]
            try:
                infos = page.get_images(full=True)
            except Exception as e:
                log.warning("page image listing failed page=%s err=%s", page_number_1, e)
                continue
            masked = {info[1] for info in infos if len(info) > 1 and info[1]}
            index = 0
            for info in infos:
                xref = info[0]
                if not xref or xref in masked:
                    continue  # reference-less entry or alpha mask, not an image
                try:
                    extracted = doc.extract_image(xref)
                except Exception as e:
                    log.warning(
                        "image extraction failed page=%s xref=%s err=%s",
                        page_number_1,
                        xref,
                        e,
                    )
                    continue
                ext = str(extracted.get("ext", "")).lower()
                if ext not in _ALLOWED_EXTENSIONS:
                    log.debug(
                        "unsupported image encoding skipped page=%s xref=%s ext=%s",
                        page_number_1,
                        xref,
                        ext,
                    )
                    continue
                raw = bytes(extracted.get("image") or b"")
                if not raw:
                    continue
                images.append(
                    RawImage(
                        page_number=page_number_1,
                        image_index=index,
                        width=int(extracted.get("width") or 0),
                        height=int(extracted.get("height") or 0),
                        mime_type=_ALLOWED_EXTENSIONS[ext],
                        ext=ext,
                        sha256=hashlib.sha256(raw).hexdigest(),
                        size_bytes=len(raw),
                        data=raw,
                    )
                )
                index += 1
        return images
    finally:
        doc.close()


def filter_images(
    images: list[RawImage],
    *,
    min_width: int,
    min_height: int,
    min_bytes: int,
    max_per_page: int,
    max_per_doc: int,
) -> tuple[list[RawImage], dict[str, int]]:
    """Apply size floors then per-page/per-document caps. Returns (kept,
    stats) where stats carries extracted/filtered/kept for logging."""
    kept: list[RawImage] = []
    per_page: dict[int, int] = {}
    for image in images:
        if image.width < min_width or image.height < min_height:
            continue
        if image.size_bytes < min_bytes:
            continue
        if per_page.get(image.page_number, 0) >= max(1, max_per_page):
            continue
        if len(kept) >= max(1, max_per_doc):
            break
        per_page[image.page_number] = per_page.get(image.page_number, 0) + 1
        kept.append(image)
    return kept, {
        "extracted": len(images),
        "kept": len(kept),
        "filtered": len(images) - len(kept),
    }
