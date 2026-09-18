# Limitations (after PDF image extraction: storage + provenance done)

- Embedded PDF images are extracted, stored, and exposed with exact page
  provenance, but the system does NOT semantically understand image contents:
  no vision model, no image embeddings, no multimodal RAG, no image OCR
  beyond the existing page path. Unsupported encodings (jpx, jbig2, ccitt)
  and sub-threshold decor are skipped by design.
- Tutor/Quiz/Mastery/Growth/Recommendations/Admin are built and tested; the
  full learning loop runs end to end under `TEST_FAKE_AI`.
- Live Google/Groq calls are not executed by the automated suite by design
  (`TEST_FAKE_AI`); provider logic is covered by fakes + classification unit
  tests, and E2E runs the full pipeline with deterministic content-derived
  fakes. Live verification (2026-09-18): `models/gemini-embedding-001`
  (768-d truncation) embeds + stores pgvector rows; `openai/gpt-oss-20b`
  answers grounded tutor questions with citations and generates quizzes
  (note: reasoning model — keep token budgets generous). Retired model names
  (`llama-3.1-8b-instant`, `text-embedding-004`) were replaced accordingly.
- Live-Neon vector execution not yet run here (no `DATABASE_URL`); SQLite
  behavior plus PostgreSQL statement compilation are tested — run search load
  against Neon before going live (exact scans are correct at current scale;
  revisit HNSW past ~100k chunks).

- Auth is hardened (Prompt 12: login throttle + timing parity, JWT/CORS/docs
  prod guards) with minimal learner/admin RBAC (Prompt 12.5); still deferred:
  no server-side token revocation, no refresh-token rotation, no MFA or
  breach-list checks — see `docs/SECURITY.md`. Admin bootstrap trusts
  `ADMIN_EMAILS` secrecy.
- Schema implemented (28 tables through `0010_admin_context_aiusage`) but
  **not yet validated against live Neon**: `alembic upgrade head` was verified
  via import + `alembic history` + Postgres-dialect DDL compilation, with
  behavioral tests on FK-enforced SQLite. Run `alembic upgrade head` against
  Neon before going live.
- AI evaluation is deterministic behavioral/contract checking with test
  doubles (16 cases) — no model-judge, no human review, no quality
  percentages. AI usage cost is a rough static estimate for known models,
  NULL otherwise.
- `Retriever.retrieve` raises `NotImplementedError` by design (Prompt 6).
- PaddleOCR is not installed here, so the OCR path is proven by protocol-fake
  tests plus an explicit-unavailable test — not against real PaddleOCR weights.
  Install `pip install -e ".[ocr]"` and process a scanned PDF before relying on OCR.
- Neon Object Storage is live-verified (2026-09-18: put/get/exists/delete +
  full upload → worker-processing → READY cycle against the real bucket).
  Chunk `embedding` stays NULL on new projects until knowledge processing
  embeds them (Prompt 6 placeholder behavior for unevaluated chunks).
- Celery has `ping` + `process_material` tasks; Flower optional, not required.
- Frontend shows structural empty states — no fake data anywhere.
- Performance principles adopted (async I/O, pooling, no sync long work in routes,
  pagination, bounded AI context, structured logging) but unproven at scale — no load tests yet.
