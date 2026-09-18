# RAG (Implemented — Prompt 6)

Pipeline: READY document → embed missing chunks (batches) → extract concepts →
project-scoped pgvector search → bounded context + app-built citations.

## Ingestion → embeddings

- Trigger: `process_material` chains `process_knowledge` on READY; reprocess
  endpoint resets one material and re-queues. One `knowledge.process` job row
  per material (idempotency key `material:<id>:knowledge`), same atomic-claim
  pattern as document processing (QUEUED/RETRYING or stale RUNNING lease).
- `execute_knowledge_processing` embeds only chunks with `embedding IS NULL`
  (resume-safe), commits per batch, then extracts concepts. Duplicate delivery
  and already-complete runs are no-ops without duplicate events.
- Vectors are validated (count, exact 768 width, finite) before any write.

## Chunking (unchanged from Prompt 5)

Deterministic, page-aware chunks with `page_start`/`page_end`; overlap stays
within pages. Chunk identity (`document_id`, `chunk_index`) is stable, which is
what makes resume and citation provenance sound.

## Embeddings / pgvector

- Single store: PostgreSQL + pgvector, existing `VECTOR(768)` column, no new
  tables or migrations for vectors.
- Retrieval orders by cosine distance (`<=>`) with an explicit similarity
  threshold (`similarity = 1 - distance`). Embeddings never leave the backend
  (no API field carries a vector; asserted in tests).
- No approximate index (exact project-scoped scans per the documented scale
  decision). SQLite test/E2E fallback computes identical cosine ordering in
  Python; the real PG statement is compile-validated (`WHERE project_id`,
  `<=>`, `IS NOT NULL`).

## Project-scoped retrieval

- `RetrievalService.search`: authenticate → authorize project (404 otherwise)
  → embed query → SQL with mandatory `document_chunks.project_id` predicate
  (+ optional material filter, archived materials excluded) → threshold filter
  → top-k clamp (≤50). There is no global retrieval path.
- Returns `query`, `results` (chunk/document/material ids, text, pages,
  similarity), `citations` (app-constructed from provenance), `context`,
  `insufficient_evidence`.

## Similarity threshold / quality controls

- `RAG_TOP_K`, `RAG_SIMILARITY_THRESHOLD`, `RAG_MAX_CONTEXT_CHUNKS`,
  `RAG_MAX_CONTEXT_CHARS` from Settings, clamped server-side
  (top_k 1–50, threshold 0–1, context ≤200k chars).
- Empty results or best-similarity-below-threshold → `insufficient_evidence:
  true`, empty context, no manufactured answer (the Prompt 7 Tutor contract).

## Tutor consumption (Prompt 7)

- `TutorService` reuses `RetrievalService.search` directly — no second RAG
  implementation. Grounded questions render retrieved chunks as labeled
  `[Source N]` blocks (no trust-boundary delimiters; `build_tutor_prompt`
  owns the single `SOURCE_BEGIN/END` wrapper), and citations are rebuilt from
  `SearchResult.citations` (chunk/document/material ids + app-side pages).
- Deterministic `classify_intent` routes `PROJECT_GROUNDED` (material/page
  references) vs `GENERAL_LEARNING` vs `CLARIFICATION` (history-relative) vs
  `UNSUPPORTED` (universal destructive/credential/admin/tool actions, refused
  before retrieval). No model call, no side effects.

## Context building

- `build_rag_context`: similarity-desc order, exact-duplicate collapse (first
  wins, provenance kept), per-chunk `Material — Page X` headers, char budget
  with truncation flag. Deterministic.

## Citations

- `Citation{material_id, material_name, document_id, page_start/end,
  chunk_id}` built only from retrieved rows; labels render as
  `Material — Page X`. Page numbers are never invented — the model never
  constructs citations.

## Prompt-injection boundary

- Retrieved/document text is untrusted data. Prompts keep three zones
  (`SYSTEM INSTRUCTIONS` / `UNTRUSTED SOURCE MATERIAL … END`); concept
  extraction additionally instructs the model to treat embedded instructions
  as data. Delimiters are hygiene, not proof: the guarantees are Pydantic
  validation, app-owned citations, and no tools/auth/DB access from model
  output. See `docs/SECURITY.md`.

## Image evidence (extensibility only)

- `format_image_references` renders extracted `DocumentImage` rows as
  `[IMAGE]` metadata blocks (document, page, index, type, dimensions) for a
  future multimodal retriever. It is NOT wired into the default text context:
  retrieval scoring, pgvector dimension (768), and text behavior are
  unchanged, and image binaries never enter embeddings.
- The blocks describe where images exist and MUST NOT claim anything about
  image contents — no vision model reads them yet (see Limitations).

## Limitations

- Concept relationships limited to existing enum types
  (`PREREQUISITE`, `RELATED`, `PART_OF`, `DEPENDS_ON`); unknown types dropped.
- Concept provenance is material-granular (chunk lists per material), never
  LLM-attributed per chunk.
- Images are stored/exposed with exact page provenance but not semantically
  understood: no vision model, no image embeddings, no multimodal retrieval.
  The planned future path is `PDF image → vision model → description →
  retrieval → Tutor citation` in a later phase.
- Live-Neon vector execution not yet run in this environment (no
  `DATABASE_URL`); SQLite behavior + PG compilation are tested.

## Future HNSW/scaling considerations

- Past ~100k chunks, add HNSW (`vector_cosine_ops`) in a migration; the
  project predicate composes with index scans. Until then exact scans win on
  simplicity and recall.
