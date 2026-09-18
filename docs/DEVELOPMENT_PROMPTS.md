# Development Prompts

Actual material prompts used with the AI development agent (OpenCode / Muse
Spark), organized by phase. Prompts 1–6 ran in earlier sessions and are
summarized, not reproduced verbatim; Prompts 7–12.5 are the verbatim task
briefs received in this session (content preserved, formatting condensed).

## 1. Architecture

Brief: modular monolith (React/Vite → FastAPI → services → PostgreSQL/pgvector,
Celery+Redis, S3-compatible object storage, Groq + Gemini). Preserve the
architecture across all later prompts; no microservices, no parallel
implementations.

## 2. Foundation

Prior-session briefs: repo scaffolding, versioned API + health probes, error
envelope, request IDs, structured logging, CORS, centralized settings, DB
session, Alembic chain, CI skeleton, hermetic test guards.

## 3. Database

Prior-session briefs: 24-table learning domain (users → spaces → projects →
materials/documents/chunks/images → concepts → tutor → assessment → mastery →
growth → recommendations → events → jobs), composite-FK project isolation,
pgvector VECTOR(768), additive single-head migrations 0001–0004.

## 4. Authentication

Prior-session briefs: Argon2id, short-lived JWT (sub/typ/iat/exp/jti),
generic login failures, audit events, ownership dependencies with
non-disclosing 404s. (No roles — RBAC was deferred to gap closure.)

## 5. Spaces/Projects

Prior-session briefs: space/project CRUD with archive/restore, workspace UI,
ownership scoping, IDOR matrices.

## 6. Materials/PDF processing

Prior-session briefs: PDF validation (extension/MIME/magic/size), server-side
storage keys, QUEUED→PROCESSING→READY/FAILED via Celery with atomic claims +
stale-lease reclaim, PyMuPDF extraction, deterministic chunking, embedded
image extraction with page provenance, local/R2 storage abstraction.
(Migration to Neon Object Storage arrived later as Prompt 12B.)

## 7. Knowledge/RAG

Verbatim brief: grounded Tutor over project RAG with app-built citations and
explicit insufficient-evidence handling; retrieval contracts, provenance,
injection boundaries; fake AI doubles (`TEST_FAKE_AI`) for deterministic
tests; real providers behind settings only.

## 8. Tutor

Verbatim brief (Prompt 7): *"Design and implement the AI Tutor feature ... Keep
the existing architecture intact — do NOT rebuild or restructure the project.
... Tutor must use the Current Project context, including project materials,
relevant concepts, previous conversation context, assessment history, and
important learning context ... Grounded answers ... Meaningful citations ...
Explicit unsupported/insufficient-evidence handling ... Prompt-injection
protection ... Controlled application interaction ... Do NOT process the PDF
synchronously ... Preserve QUEUED/PROCESSING/READY/FAILED ... Do NOT add
voice/flashcards/social ... features."* Included the full current-repo file
listing as context.

## 9. Assessment

Verbatim brief (Prompt 8): adaptive quiz engine — *"concept selection strategy,
grounded generation, MCQ/open-ended evaluation, server-side completion,
per-concept results"* — with multi-signal selection (explicitly *not*
wrong→easy/correct→hard), structured open-ended evaluation (understanding,
accuracy, relevance, concepts covered/missing, reasoning), explanatory
feedback, immutable results, idempotency, cross-tenant tests.

## 10. Mastery

Verbatim brief (Prompt 9): deterministic per-concept mastery/confidence/trends
with immutable history, explanations, and Tutor + quiz integration — *"No LLM
anywhere"* in the mastery update path, idempotent application, EWMA-style
estimates framed as estimates.

## 11. Growth/Recommendations

Verbatim brief (Prompt 10): project growth status/counts/history derived from
mastery history; deterministic recommendation rules with lifecycle and dedup
(`uq_recommendations_active_scope`), Growth + Recommendations UI.

## 12. Analytics

Verbatim brief (Prompt 11): read-only project analytics (aggregates, event
feed, charts), 22-test E2E suite with real Celery worker, `scripts/smoke_test.py`
full-loop smoke.

## 13. Production hardening

Verbatim brief (Prompt 12): *"make the existing application safer, more
reliable, observable, performant, and deployment-ready — without rebuilding
architecture ... Fix real vulnerabilities rather than documenting them ... Keep
the repo runnable ... complete learning loop intact."* Produced: request-ID
validation, CORS/docs prod guards, login throttle + timing parity, Groq
timeouts, pool settings, 429 envelope, `test_security.py`, smoke script,
threat-model docs, CI gates.

## 14. PRD gap closure (this task)

Verbatim brief (Prompt 12.5): close *only* remaining compulsory PRD v3.0
requirements against the existing implementation — audit first, implement
admin RBAC + dashboard, global analytics, home/continue-learning, persistent
learning context, repeated-mistake workflow, AI usage persistence, evaluation
framework, traceability + admin/context/evaluation/prompt docs, full
validation. Explicitly excluded streaming/voice/flashcards/spaced-repetition
and other optionals.

## 15. Testing/deployment

Recurring briefs across prompts: backend `pytest` + `ruff check` +
`ruff format --check` + `mypy app`; frontend typecheck/lint/format/test/build;
Playwright E2E with real worker; `alembic heads/history`; startup/OpenAPI/
worker/health checks; secret sweeps; honest reporting
(VERIFIED LOCALLY vs TEST DOUBLE vs REQUIRES REAL PROVIDER).
