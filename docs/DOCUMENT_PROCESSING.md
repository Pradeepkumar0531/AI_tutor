# Document Processing (Implemented — Prompt 5)

Target pipeline (embeddings/concepts arrive in Prompt 6):

```
upload → storage → queue → worker → PyMuPDF extract → OCR fallback (PaddleOCR
preferred, Tesseract CLI fallback) → normalize → chunk → Document +
DocumentChunks + DocumentImages → READY
```

## Stages

| Stage | Code | Notes |
|---|---|---|
| Validate | `app/documents/validation.py` | MIME + extension + `%PDF-` magic + size; never trusts one signal |
| Store | `app/storage/` | Local fs (dev) or Neon Object Storage via boto3 S3 API (prod); server-side keys only |
| Enqueue | `app/jobs/dispatch.py` post-commit | Broker outage → job stays QUEUED, upload still 201 |
| Claim | `execute_material_processing` | Atomic `UPDATE … WHERE status IN (QUEUED, RETRYING)` (+ stale-lease reclaim); losers ack without work |
| Extract | `app/documents/extract.py` | PyMuPDF per-page text, 1-based page numbers, title/author |
| OCR | `app/documents/ocr.py` | Only fully-empty pages; PaddleOCR preferred when the `[ocr]` extra is installed, otherwise the `tesseract` CLI binary; both optional via protocol, loud failure when neither exists |
| Normalize | `app/documents/normalize.py` | Collapse spaces/blank runs, strip controls, keep paragraphs + tabs |
| Chunk | `app/documents/chunking.py` | Deterministic, page-aware, overlap within pages |
| Images | `app/documents/images.py` | Embedded rasters via `doc.extract_image` (original bytes, png/jpg/gif/bmp/webp); alpha masks skipped; size floors + per-page/per-doc caps; SHA-256 content keys |
| Persist | worker transaction | Delete-then-insert rebuild; `documents.material_id` unique; images stored through `StorageService` in the same transaction as READY |

## Embedded image extraction

- Per page, `page.get_images(full=True)` xrefs resolve to original bytes
  (`doc.extract_image`); alpha-mask xrefs and unsupported encodings (jpx,
  jbig2, ccitt, …) are skipped with counts. No page screenshots, no vector
  objects, no re-encoding.
- Filtering (`PDF_MIN_IMAGE_WIDTH/HEIGHT=100`, `PDF_MIN_IMAGE_BYTES=2048`,
  `PDF_MAX_IMAGES_PER_PAGE=10`, `PDF_MAX_IMAGES_PER_DOCUMENT=50`): below
  100px/2KB is decor (logos, icons, bullets, tracking pixels); caps keep the
  first images in document order. Disable entirely with
  `PDF_IMAGE_EXTRACTION_ENABLED=false`. Extraction failure never fails text
  processing (enhancement-only, logged).
- Deduplication is content-addressed: storage key
  `projects/{pid}/materials/{mid}/images/{sha256}.{ext}` — identical binaries
  (e.g. repeated headers) share one object via idempotent puts, while every
  page placement keeps its own `DocumentImage` row (`document, page_number,
  image_index` unique) so provenance is exact.
- Persist runs in the READY transaction: unique binaries put first, rows
  second, READY last — a material is never READY with partial image state.
  Storage errors follow the transient retry/fail path; just-written objects
  with no references are deleted best-effort, as are keys superseded by a
  rebuild. Re-running a READY material is a no-op; retries rebuild cleanly.
- Observability: one summary line per material
  (`pages/extracted/stored/duplicates/filtered`) with ids only — never image
  contents, keys, or secrets.

## The transition to knowledge (Prompt 6)

```text
PDF extraction
→ chunks (DocumentChunk rows, embedding NULL)
→ knowledge job chained on READY (job_type knowledge.process)
→ embed missing chunks in batches (Google text-embedding-004, validated 768-d)
→ extract concepts via Groq structured JSON (validated, deduped, project-scoped)
→ knowledge ready (derived status: PENDING / PROCESSING / READY / FAILED)
```

Document state never regresses on knowledge failure: the material stays READY,
embeddings persist for resume, and only the knowledge job is marked FAILED.

## Rules that must survive future prompts

- HTTP never runs the pipeline synchronously; the worker needs no request context.
- One logical Document per Material; chunks carry `page_start`/`page_end`.
- `embedding` stays NULL until Prompt 6 — nothing in this phase writes vectors.
- OCR (`paddleocr`) is an optional extra (`pip install -e ".[ocr]"`) due to its weight.
- No LangChain, no tokenizers, no AI calls in ingestion.

## Retries & failure

- Transient (storage/network/DB): bounded Celery retries, backoff `min(300, 15·2ⁿ)`s,
  max 3 attempts; then FAILED with a safe message.
- Permanent (corrupt PDF, no content, OCR unavailable when needed, over-limit,
  missing object): immediate FAILED, no retry.
- Stale RUNNING claims (> `PROCESSING_STALE_CLAIM_MINUTES`, default 30) may be
  reclaimed — crash recovery without memory locks or Redis flags.
