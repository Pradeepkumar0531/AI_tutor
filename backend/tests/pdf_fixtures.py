"""Deterministic in-memory PDF fixtures. Built with PyMuPDF textboxes (which
extract with spaces preserved) — no binary blobs committed to the repo."""

from __future__ import annotations


def make_text_pdf(pages: list[str]) -> bytes:
    """One textbox page per entry; realistic extractable text."""
    import pymupdf

    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 500, 700), text)
    return bytes(doc.tobytes())


def make_blank_pdf(*, pages: int = 1) -> bytes:
    """Pages with no text at all (scanned/empty-document stand-in)."""
    import pymupdf

    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page()
    return bytes(doc.tobytes())


def make_noise_pixmap(width: int, height: int, *, seed: int = 7):
    """Deterministic noisy RGB pixmap: compresses to kilobytes (passes the
    minimum-bytes filter), unlike solid fills."""
    import random

    import pymupdf

    rng = random.Random(seed)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.Rect(0, 0, width, height))
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            pix.set_rect(
                pymupdf.Rect(x, y, x + 4, y + 4),
                (rng.randrange(256), rng.randrange(256), rng.randrange(256)),
            )
    return pix


def make_image_pdf(pages: list[dict] | None = None) -> bytes:
    """PDF with embedded raster images. Each entry: {"text": str, "images":
    [(width, height, seed)]}. One textbox + placed pixmaps per page; image
    placement order defines the deterministic page-local index."""
    import pymupdf

    if pages is None:
        pages = [
            {
                "text": "Photosynthesis converts sunlight into chemical energy.",
                "images": [(300, 200, 7)],
            },
            {"text": "Mitochondria release energy as ATP.", "images": [(300, 200, 7)]},
        ]
    doc = pymupdf.open()
    for entry in pages:
        page = doc.new_page()
        if entry.get("text"):
            page.insert_textbox(pymupdf.Rect(72, 72, 500, 150), entry["text"])
        y = 170
        for width, height, seed in entry.get("images", []):
            pix = make_noise_pixmap(width, height, seed=seed)
            page.insert_image(pymupdf.Rect(72, y, 72 + width, y + height), pixmap=pix)
            y += height + 20
    return bytes(doc.tobytes())


def make_scanned_pdf(pages: list[str], *, dpi: int = 200) -> bytes:
    """Genuine scanned-PDF equivalent: render text pages to raster, then build
    a new PDF from the pixels alone. Zero extractable text, real letterforms
    — exercises the true OCR fallback path (no mocks, no PIL needed)."""
    import pymupdf

    src = pymupdf.open()
    for text in pages:
        page = src.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 500, 700), text)
    doc = pymupdf.open()
    for src_page in src:
        pix = src_page.get_pixmap(dpi=dpi)
        page = doc.new_page(width=pix.width * 72 / dpi, height=pix.height * 72 / dpi)
        page.insert_image(page.rect, stream=pix.tobytes("png"))
    return bytes(doc.tobytes())


def make_corrupt_pdf() -> bytes:
    """Right magic, garbage body: passes upload validation, fails extraction."""
    return b"%PDF-1.4\n" + b"\x00\xff not a real pdf body" * 100


def make_not_a_pdf() -> bytes:
    return b"This is plain text, not a PDF at all."


LOREM = (
    "Learning is the acquisition of knowledge through study and experience. "
    "Spaced repetition strengthens long-term retention of new concepts. "
    "Active recall outperforms passive re-reading in most controlled trials."
)
