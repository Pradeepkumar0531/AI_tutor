# Testing

Backend: `cd backend && pytest` (hermetic: `tests/__init__.py` points
`APP_ENV_FILE` at the null device and scrubs ambient infrastructure secrets, so
a developer's real `backend/.env` can neither break nor be touched by the suite
— SQLite/local storage only; same guard in `scripts/smoke_test.py`) —
- `test_foundation.py` (startup, health, readiness, request IDs, error envelope,
  Argon2id, JWT roundtrip; Prompt 1, still passing),
- `test_domain_models.py` (constraints, defaults, cascades, uniqueness, ordering),
- `test_project_isolation.py` (two-tenant matrix: scoped repos return `None`
  cross-tenant; service gates raise `NotFoundError`, i.e. 404, never 403),
- `test_auth.py` (registration/login/token edge cases, `/me`, logout, HTTP IDOR
  matrix over real endpoints, CORS allow-list, no secret/hash/token leakage),
- `test_spaces_projects.py` (space/project CRUD, PATCH allow-list, archive/restore,
  pagination, escaped search, counts, `SPACE_CREATED`/`PROJECT_CREATED` events,
  full cross-tenant matrix incl. PATCH/DELETE/restore and space-filtered listing),
- `test_materials.py` (PDF validation incl. magic bytes, local roundtrip +
  traversal rejection, Neon provider mocked S3 put/get/head/delete + error
  mapping + missing-config fail-fast + provider selection, upload API incl.
  rollback/compensation, authz matrix, detail/document/chunk pagination,
  reprocess rules, archive/restore),
- `test_processing.py` (normalize/chunk determinism + page-awareness, READY path
  with metrics/events, blank/corrupt/oversize failures, fake-protocol OCR path,
  OCR-unavailable loud failure, transient retry→success and exhaustion, claim
  loss + stale reclaim, idempotent reruns, chunk determinism, dispatch contract,
  task registration),
- `test_ai.py` (config defaults + dimension-mismatch refusal, fake embedding
  shape/order/batching, dimension/count/non-finite rejection, transient retry
  vs permanent no-retry, timeout surfacing, Groq JSON success/malformed +
  transient classification, concept DTO validation, prompt trust boundary,
  AI log format without secrets, content-derived keyword concepts),
- `test_knowledge.py` (knowledge status matrix PENDING/PROCESSING/READY/FAILED,
  concept upsert dedupe + provenance merge, relationship validation incl.
  DB-level cross-project refusal, reprocess rules, material-detail knowledge
  summary, full HTTP contracts: search shape, 401/404s, pagination, limits,
  no-embedding-leak, insufficient evidence),
- `test_knowledge_jobs.py` (end-to-end embed+extract job, partial resume,
  duplicate delivery, claim loss + stale reclaim, transient/permanent/concept
  failure paths, exhaustion bound, knowledge-failure-keeps-READY, chain wiring,
  task registration),
- `test_rag.py` (nearest-neighbor ordering, threshold/top-k/clamps, empty and
  blank-query behavior, cross-tenant denial, material filter + archived
  exclusion, no-embedding/key leak, context provenance/budget/dedup, citation
  labels, adversarial-text-stays-data, PG `WHERE project_id` + `<=>` compile
  checks, `VECTOR(768)` DDL),
- `test_tutor.py` (intent routing incl. universal-action refusal, conversation
  CRUD + `CONVERSATION_CREATED`/`TUTOR_RESPONSE` events, grounded flow with
  app-built citations, insufficient/general/unsupported paths, prompt-injection
  stays-data, history bounding, user-persisted-on-failure, `request_key`
  replay + unique constraint, cross-tenant 404 matrix, missing-key/timeout/
  malformed-output mapping),
- `test_assessment.py` (selection strategy incl. mistake-weighting/coverage/
  determinism/mastery-hook, quiz creation incl. bounds/focus/idempotency/
  malformed/transient/insufficient/provenance, attempts incl. resume/READY
  gates, MCQ matrices, open-ended correct/partial/incorrect/malformed/bounded/
  injection, completion incl. scoring/concept aggregation/duplicates/
  post-completion rejection, full IDOR matrix, QuestionConcept DB isolation,
  route learner-safety),
- `test_mastery.py` (28: exact algorithm numerics incl. cold start, partials,
  diminishing returns, non-replacement, decay, trends, bounds, determinism;
  persistence incl. history provenance, idempotency, rollback, rebuild;
  API incl. pagination/sorts/cold-start/405/isolation; completion/tutor/quiz
  integration; assessment immutability),
- `test_document_images.py` (22: extraction incl. masks/dedup/MIME/dims/hash,
  filtering incl. tiny/caps/disable/oversized, pipeline counts, storage keys/
  containment/roundtrip/missing, job persist incl. idempotent rerun,
  storage-failure retry without orphans, rebuild orphan cleanup, service
  list/get/bytes, missing-binary 404, full isolation matrix, detail/knowledge
  counts, route learner-safety + bytes, RAG metadata-only helper, text-only
  regression, cross-project DB rejection),
- `test_services.py` (schema non-exposure, atomic commit, rollback on failure),
- `test_growth.py` (23: status rules, cold start, overall/counts, per-concept
  rows, improving/attention states, history, confidence semantics; generation,
  priority, evidence-vs-noise, declining, cold exclusion, dedup/regeneration,
  lifecycle conflicts, expiry, material/assessment relationships, action
  mapping; full-flow chain, downstream-fault survival; routes incl. isolation;
  growth/rec isolation matrix),
- `test_analytics.py` (14: event record validation/sanitization, feed order/
  filter/pagination/date bounds, empty vs populated dashboard incl. archived
  exclusion, material/knowledge/tutor counts, timeline summaries + filter +
  invalid types, zero-filled/all-time day series + bounds, mastery-trend
  reuse, sub-30-statement dashboard budget, routes incl. 422s, full
  dashboard/events isolation matrix),
- `test_security.py` (26: JWT accept/reject matrix incl. disabled accounts,
  request-ID validation/echo, error-envelope + request-id linkage, CORS prod
  guard, docs hidden in prod, login throttle trip/reset/generic errors, mass
  assignment drops, answer-score rejection, upload 413/magic/traversal-safe
  keys, events/analytics/growth/recommendation/quiz-attempt IDOR, injection
  boundary incl. image-bytes and forced-answer probes, envelope codes
  400/401/403/404/409/413/422/429/500/503 without leakage),
- `test_pg_dialect.py` (all 28 tables compile for PostgreSQL; `VECTOR(768)`;
  migration chain covers extension + tables + enums),
- `test_admin.py` (RBAC matrix: learner→403/anon→401/disabled→403/unknown→401,
  `ADMIN_EMAILS` bootstrap on register + login, overview/users/journey/
  activity-filters/jobs/health secret-free, AI usage, evaluation run 16/16),
- `test_learning_context.py` (weakness/strength/pattern derivation, single
  miss ≠ pattern, idempotent rewrite, bounded project-scoped retrieval,
  targeted rec + no-duplicate refresh),
- `test_ai_usage.py` (record/summary/count, known/unknown-model cost honesty,
  user scoping),
- `test_ai_evaluation.py` (registry covers 4 categories; 16/16 pass with
  fakes; machine-readable persisted run),
- `test_home_global.py` (home/global aggregates, cold-start honesty, cross-user
  isolation, auth required).
No `DATABASE_URL` here, so tests run on FK-enforced SQLite (`tests/conftest.py`);
Postgres rendering is asserted via dialect compilation. Config: `pytest.ini_options`
in `pyproject.toml`.

Frontend: `cd frontend && npm test` (Vitest: empty-state render, API base URL
config, auth store login/logout/initialize, `RequireAuth` redirects, spaces /
projects stores + pages incl. empty/error states, create flows, archive updates,
workspace placeholders with a no-fake-metrics assertion, materials store /
upload dialog validation / status badges / polling start-stop / detail with
chunk pagination — network
boundary mocked at the Axios singleton only; knowledge suite covers store,
status/concepts/search/insufficient-evidence/error/retry states and citation
rendering; tutor suite covers store auto-create/dedupe/send/reload/error
states plus component badges, citations, empty states, in-flight disable, and
conversation switching; assessment suite covers store create/answer/complete/
history flows plus component feedback reveals, progress, result performance,
and empty states; mastery suite covers store list/detail/history/sort plus
component scores, cold-start honesty, history transitions, and empty states;
material-images suite covers store fetch/error plus section metadata, empty/
processing/error/preview-failure states; growth suite covers store
list/detail/history/sort plus overview/distribution/chart/cold-start states;
recommendations suite covers store list/complete/dismiss plus cards, actions,
empty states, and lifecycle; dashboard suite covers store slices, summary
cards/links, charts, timeline, cold-start/thin-history honesty, partial
failure, and retry). E2E: `npx playwright test` boots
frontend + API + a real Celery worker subprocess (isolated SQLite, filesystem
broker, fresh schema and a generated 2-page PDF per run via `global-setup.ts`,
deterministic fake AI via `TEST_FAKE_AI=true`)
and walks register → upload → worker-driven READY → knowledge READY →
concepts with provenance → grounded search with page citations → refresh →
logout, plus corrupt-PDF failure display and cross-tenant matrices
(B cannot read/reprocess/delete A's material or document, or search A's
project, via API and browser). `assessment.spec.ts` walks the same fixture
through quiz generation → READY → attempt → MCQ (first-option-correct fake
contract) + open-ended answers → completion → assessment with concept
performance → reload → history restore → logout, plus an adaptive test where
a missed concept resurfaces in the next quiz despite unseen alternatives.
Production smoke: `scripts/smoke_test.py` (`TEST_FAKE_AI=true`, throwaway
SQLite + storage) walks health → register → login → me → space → project →
upload → real worker document + knowledge functions → RAG → tutor → quiz →
complete → mastery → growth → recommendations → dashboard → events → logout
(24 checks, no server or broker needed).
`dashboard.spec.ts` walks tutor interaction → mixed quiz → dashboard cards,
charts, and timeline from real persisted state → reload → logout, plus a
dashboard/events tenant-isolation matrix (UI + raw API). `mastery.spec.ts`
walks completion → synchronous mastery update → list/
detail/history → a second assessment moving estimates → reload persistence →
logout, plus an assessment→mastery→quiz-selection loop asserting the missed
concept resurfaces with sub-50% persisted mastery. `growth.spec.ts` walks
completion → growth overview with distribution → recommendations with reasons
and real actions → practice navigation → complete/dismiss lifecycle → reload
persistence → logout, plus an assessment→mastery→quiz loop and a
growth/recommendation tenant-isolation matrix (UI + raw API). `images.spec.ts` walks
upload of a PDF with an embedded raster → worker extraction → READY →
material detail with image counts/provenance/thumbnail → reload persistence
→ logout gating, plus a tenant-isolation matrix (UI + raw API on list,
metadata, and bytes). `tutor.spec.ts` walks the same fixture through
grounded answer + citation badge → insufficient/general/unsupported/injection
fallbacks → reload persistence → `request_key` replay collapsing to one
exchange (raw API) → logout gating, plus a tenant-isolation matrix (B gets
404 on A's conversation list and sends, via API and browser). Tutor E2E gates
on full worker completion (exact `2/2 chunks embedded` + concept button):
badge/counter-only waits race embedding and yield false insufficient answers.
Config: `pytest.ini_options` in `pyproject.toml`; Vitest jsdom + `src/test/setup.ts`.
