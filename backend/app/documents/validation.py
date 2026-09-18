"""Upload validation + server-side storage key design.

Validation uses multiple signals (declared type, extension, magic bytes, size)
because browsers can lie about MIME types. Keys are generated server-side from
database UUIDs only — the original filename never touches the filesystem path.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from app.core.exceptions import BadRequestError


class UploadValidationError(BadRequestError):
    code = "INVALID_UPLOAD"
    message = "Invalid upload."


class UploadTooLargeError(BadRequestError):
    code = "UPLOAD_TOO_LARGE"
    status_code = 413
    message = "File exceeds the maximum upload size."


ALLOWED_CONTENT_TYPES = frozenset({"application/pdf"})
ALLOWED_EXTENSIONS = frozenset({".pdf"})
PDF_MAGIC = b"%PDF-"
# Per the PDF spec the header lives in the first bytes; tolerate a small
# leading run of whitespace/BOM-like bytes from quirky producers.
_MAGIC_SEARCH_WINDOW = 1024


@dataclass(frozen=True)
class ValidatedUpload:
    filename: str  # sanitized display name only, never a path
    content_type: str
    size_bytes: int
    sha256: str


def _display_filename(raw: str | None) -> str:
    name = (raw or "").strip().replace("\\", "/").split("/")[-1].strip()
    name = "".join(c for c in name if ord(c) >= 32)
    return name[:255] or "document.pdf"


def validate_pdf_upload(
    *,
    filename: str | None,
    content_type: str | None,
    data: bytes,
    max_bytes: int,
) -> ValidatedUpload:
    """Validate a candidate PDF upload. Raises 400/413 — never trusts one signal."""
    if not data:
        raise UploadValidationError("Uploaded file is empty.")
    if len(data) > max_bytes:
        raise UploadTooLargeError(f"File is {len(data)} bytes; limit is {max_bytes} bytes.")
    name = _display_filename(filename)
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(f"Unsupported file type {ext!r}: only PDF is accepted.")
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared and declared not in ALLOWED_CONTENT_TYPES:
        raise UploadValidationError(f"Unsupported content type {declared!r}: only PDF is accepted.")
    window = data[:_MAGIC_SEARCH_WINDOW].lstrip(b" \t\r\n\x00\xef\xbb\xbf")
    if not window.startswith(PDF_MAGIC):
        raise UploadValidationError("File does not look like a PDF (missing %PDF- header).")
    return ValidatedUpload(
        filename=name,
        content_type="application/pdf",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


def build_storage_key(*, project_id: uuid.UUID, material_id: uuid.UUID) -> str:
    """Collision-resistant server-side key. UUIDs only — no user input."""
    return f"projects/{project_id.hex}/materials/{material_id.hex}/original.pdf"
