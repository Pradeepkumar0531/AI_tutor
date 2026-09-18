# Security

## Threat model (Prompt 12 — what is claimed vs what is not)

| Area | Threat | Mitigation (verified) | Remaining limitation |
|---|---|---|---|
| Authentication | Credential stuffing, token forgery | Argon2id; per-email failed-login throttle (10/5min → 429); JWT sub/typ/iat/exp/jti validated; prod secret guard | No MFA, no breach-list checks, no server-side revocation (short-lived tokens) |
| Authorization | IDOR, cross-tenant reads, admin bypass | Ownership deps on every route; composite-FK same-project guarantees; `require_admin` on admin routes; 403/404 matrix tests | Admin bootstrap relies on env secrecy |
| Tenant isolation | Cross-project/user leakage | Non-disclosing 404s; SQL-level project predicates; sanitized event feed | Relies on code review + matrix tests, not row-level security |
| File uploads | Malicious PDFs, traversal, bombs | Extension + MIME + magic bytes + 25MB cap server-side; UUID-only storage keys; page/image caps | No AV scanning; 25MB transient worker memory per file |
| Storage | Path traversal, public buckets | `_check_key` + containment resolve; Neon bucket private, no signed URLs; bytes via authed API | Local dev dir must have correct fs permissions (ops concern) |
| Prompt injection | Instruction override via docs/answers | Delimited untrusted zones; validated structured output; app-owned citations/scores; injection test matrix | No formal guarantee — defense in depth, not proof |
| RAG isolation | Cross-project chunks, invented citations | Mandatory project predicate in SQL; archived exclusion; app-built citations; insufficient-evidence default | Exact-scan cost grows with corpus (HNSW later) |
| AI providers | Key leaks, hanging calls, cost blowups | Env-only keys; finite timeouts; bounded retries/top-k/counts; no keys/prompts/answers in logs | Live providers unverified here (no credentials) |
| Background jobs | Duplicate/lost work, poison tasks | Atomic claims + stale-lease reclaim; bounded retries; permanent/transient split; idempotent rebuilds | Single-queue Celery; no dead-letter UI |
| Database | Injection, pool exhaustion, bad migrations | SQLAlchemy bound params; modest configurable pool; single-head additive migrations | No RLS; Neon upgrade untested here |
| Secrets | Committed credentials | Sweep clean; `.env` ignored; placeholders only in examples/tests | Operator must set prod secrets (startup guards help) |
| Frontend | XSS, token theft, UI spoofing | React text rendering (no raw HTML); token in one module; generic error boundary (no internals leaked) | localStorage token is XSS-sensitive by design — no inline scripts/unsanitized HTML anywhere |

## Authentication architecture

- **Module**: `backend/app/auth/` (`password.py`, `tokens.py`, `service.py`,
  `dependencies.py`, `exceptions.py`, `schemas.py`, `router.py`). Crypto primitives
  stay in `app/core/security.py`, which delegates to the single token
  implementation — no duplicated JWT parsing anywhere.
- **Passwords**: Argon2id only. Centralized policy (`MIN 8 / MAX 128`, reject
  blank; never stripped/truncated). Hashes never leave the server: no response
  schema, log line, event payload, or analytics field carries one.
- **JWT access tokens**: claims `sub` (user id), `typ: "access"`, `iat`, `exp`,
  `jti` (audit/future revocation). Nothing else — no email, no project lists, no
  learning data. Default lifetime 30 min (`ACCESS_TOKEN_EXPIRE_MINUTES`).
  Validation rejects expired, malformed, wrong-signature, wrong-type,
  subject-less tokens and tokens for nonexistent users.
- **Production secret guard**: issuing a token with the dev default, any known
  placeholder (including the `.env.example` value), or a <32-char
  `JWT_SECRET_KEY` under `APP_ENV=production` raises `RuntimeError` instead of
  silently minting weak tokens (`require_jwt_secret` blocklist).
- **Session**: stateless Bearer token. Frontend stores it in exactly one module
  (`frontend/src/api/tokenStorage.ts`); the Axios client attaches it and the
  auth store writes/clears it. No component touches the raw credential.
- **Logout**: `POST /auth/logout` writes a `USER_LOGOUT` audit event; the client
  always drops its token copy, even if the call fails. There is **no server-side
  JWT revocation** in this phase — a logged-out token remains technically valid
  until its short expiry. Documented tradeoff, not a hidden gap.
- **Roles**: minimal RBAC — `users.role` (`learner`/`admin`, migration
  `0010`), server-side `require_admin` on every `/api/v1/admin/*` route
  (learners 403, anonymous 401; matrix in `tests/test_admin.py`). Only
  privilege path is `ADMIN_EMAILS` bootstrap on register/login; no public
  role-setting endpoint. Admin responses are secret-free by construction
  (no hashes, tokens, keys, embeddings, or storage internals).

## Authorization model

- `get_current_user` dependency: 401 on any token problem or unknown user,
  403 (`ACCOUNT_DISABLED`) on disabled accounts.
- `get_owned_space` / `get_owned_project`: ownership-chain queries, **404**
  (`RESOURCE_NOT_FOUND`) on mismatch — cross-tenant existence is never disclosed.
- 401 = missing/invalid/expired auth. 403 = authenticated but forbidden
  (disabled account). 404 = not yours / doesn't exist (IDOR-safe default for
  resource access). All inside the shared `{error: {code, message, details,
  request_id}}` envelope.
- Isolation is enforced at the repository/query layer (`*_for_user` scoped
  methods + composite FKs on concept relationships), never in the frontend.

## Audit events

`USER_REGISTERED`, `USER_LOGIN_SUCCEEDED`, `USER_LOGIN_FAILED`, `USER_LOGOUT`
extend the existing `EventType` enum (migration `0002_auth_audit_events`).
Material lifecycle adds `MATERIAL_UPLOADED` (upload), `MATERIAL_PROCESSING_STARTED`,
`MATERIAL_READY`, `MATERIAL_FAILED` — payloads carry ids/counts only, never file
content, paths, or credentials.
Payloads carry ids/outcomes only — never passwords, hashes, or tokens. Generic
login-failure responses prevent account enumeration; failure logs carry no email.

## Knowledge, retrieval & prompt-injection defenses

- Vector retrieval is project-scoped **in SQL** (`WHERE document_chunks.project_id`),
  never fetch-then-filter; there is no global retrieval path. Archived materials
  are excluded. Cross-tenant search returns the same 404 as a missing project —
  existence is never disclosed.
- Document/chunk text is **untrusted data**: prompts separate `SYSTEM
  INSTRUCTIONS` from `UNTRUSTED SOURCE MATERIAL` blocks, concept output is
  Pydantic-validated, citations are app-constructed from chunk provenance (page
  numbers can never be model-invented), and no document content can reach tools,
  auth decisions, or database writes. Delimiters are hygiene, not proof — the
  guarantees above are structural.
- Concept relationships are constrained to existing enum types; both endpoints
  are resolved in-project and the composite-FK guarantee (`fk_rel_*_in_project`)
  rejects cross-project edges at the database level.
- AI secrets (`GOOGLE_API_KEY`, `GROQ_API_KEY`) live server-side only; AI logs
  carry provider/model/latency/counts — never keys, prompts, documents, or
  payloads. Test fakes (`TEST_FAKE_AI`) are explicit, loud, and default-off.

## Tutor defenses (Prompt 7)

- Conversations are `user → project → conversation` with repository-level
  scoping: cross-tenant conversation/message access returns 404 without
  disclosure, and the frontend never supplies user/project ids.
- Universal actions (delete/drop, credential reveal, `system prompt` /
  injection meta-requests, tool/code/SQL/admin invocation) are refused with a
  fixed message **before** retrieval or any model call; the refusal is
  persisted like any other exchange.
- Mild instruction-override text inside material scope stays data: the answer
  is generated from retrieved chunks, citations reference real chunk ids, and
  app-owned `grounded`/`insufficient_evidence` flags (never model claims)
  drive the UI badges.
- Sends are idempotent: `Message.request_key` is unique per conversation, so a
  retried POST replays the persisted exchange instead of duplicating messages;
  the user message is committed before generation, so failures never lose it.
- `GROQ_API_KEY` is required for live tutor calls; a missing key fails closed
  as `TutorGenerationFailed` (500), never as a fabricated answer.

## Quiz & assessment isolation (Prompt 8)

- Every endpoint enforces `user → project → quiz → attempt → question`;
  cross-tenant quiz/attempt/assessment/question access returns 404 without
  disclosure (tested as an IDOR matrix). The frontend never supplies
  user/project ids; concept/material/chunk ids in AI output are validated
  against the authorized project, and provenance/pages always come from
  application retrieval rows.
- Learner-safe API: pre-answer payloads contain only ids, prompts, options,
  positions, difficulty, concept labels, and source material/pages. Correct
  option ids, reference answers, and evaluator context appear only in
  post-answer feedback for the answered question. Answer validation rejects
  unknown option ids and over-length/blank text; client scores/totals are
  never trusted (completion recomputes from stored rows).
- No unrestricted AI tools: MCQ grading is deterministic code; open-ended
  evaluation is a single structured call whose output is schema-validated,
  score-clamped, and concept-filtered. Source documents and learner answers
  are untrusted data in labeled sections — injection probes (`Ignore the quiz
  instructions…`, `mark this correct…`) can alter neither scores nor
  authorization nor other projects (covered by backend + prompt tests).

## Mastery isolation and immutable history (Prompt 9)

- Mastery is scoped `(user, project, concept)` (`uq_mastery_user_project_concept`);
  every endpoint re-verifies ownership and cross-tenant reads are 404.
  Concept/project mismatches are rejected, not coerced.
- No write surface: estimates move only through assessment completion —
  arbitrary client scores are ignored/rejected (no POST/PUT/DELETE routes;
  verified 405), and history has no mutation routes.
- History rows are append-only with previous→new provenance plus the source
  assessment id; recomputation replays immutable assessments, never edits them.
- Events carry ids and scores only — no answers, prompts, keys, or AI outputs.

## Growth & recommendation isolation (Prompt 10)

- Growth aggregates and recommendations are scoped `(user, project)` with
  concept/material links re-verified project-side; cross-tenant reads and
  lifecycle transitions are 404 (tested matrix incl. concept/material/
  assessment mismatch).
- No client-writable growth or scores: estimates move only through assessment
  completion; complete/dismiss accept only ACTIVE rows (409 otherwise), and
  history has no mutation surface. Dedup is enforced by a unique scope
  constraint, not just application checks.
- Recommendation payloads carry ids, titles, templated reasons, and priority
  only — no answers, prompts, keys, or AI outputs; material references are
  project-verified names, never storage keys.

## Document image isolation (PDF image enhancement)

- Image list/metadata/bytes endpoints enforce `user → project → material →
  image`; cross-tenant or cross-material access is 404 without disclosure
  (tested matrix). Image rows additionally carry composite-FK same-project
  guarantees (`fk_docimg_document_in_project`, `fk_docimg_material_in_project`).
- Bytes are served through the authenticated API with the stored MIME type;
  the Neon bucket is never public and no signed-URL machinery exists by design
  (`url_for` refuses). Storage keys, content hashes, and filesystem paths
  never appear in learner-facing schemas; a missing binary logs server-side
  and returns 404.
- Extracted images are untrusted PDF content: bytes are stored verbatim and
  served as-is, never executed, never fed to prompts, tools, or auth
  decisions. Upload validation (MIME + `%PDF-` magic + size) still gates the
  pipeline entrance.

## Upload & processing attack surface

- PDFs only: extension + declared type + `%PDF-` magic bytes (browsers can lie
  about MIME); empty/oversize/non-PDF rejected with 400/413 before storage.
- Storage keys are server-generated UUID paths — the original filename never
  touches the filesystem; keys are validated (`..`, absolute paths, backslashes
  rejected) and local reads are containment-checked after resolution.
- Object-storage credentials live server-side only; responses/schemas/logs never contain
  storage keys, local paths, signed URLs, or stack traces (user-safe
  `processing_error` only; diagnostics in server logs).
- Workers resolve ownership from persisted rows, never client input; every
  material/document/chunk/reprocess/archive route re-verifies the full chain
  (cross-tenant matrix in `tests/test_materials.py` + E2E).
- Limits are centralized in Settings: 25 MB upload cap, 500-page / 2M-char
  caps, bounded Celery retries (max 3, no infinite loops).

## Logging

Auth logs: endpoint + outcome + user id **after** success. Never logged:
passwords, JWTs, cookies, `Authorization` headers, secrets. Verified by
`test_tokens_never_logged`.

## CORS / cookies

- No cookies in this phase, so no CSRF surface; Bearer over HTTPS in production.
- CORS is env-driven (`CORS_ORIGINS`), credentials allowed, **no wildcard
  origin**. Local: Vite ↔ FastAPI origins whitelisted by default. Production:
  startup refuses dev-default origins — `CORS_ORIGINS` must be set explicitly
  to the exact frontend origin(s).
- API docs (`/docs`, `/openapi.json`) are served in dev but hidden in
  production unless `enable_api_docs=true`.
- `VITE_*` vars are public — backend secrets must never use that prefix.

## Secrets

Only via env; `.env.example` tracked, `.env` ignored. Required for auth:
`JWT_SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `CORS_ORIGINS`, `SECRET_KEY`.

## Login brute-force protection (Prompt 12)

- Per-email sliding window: `login_max_attempts` (10) failures per
  `login_attempt_window_seconds` (300) → `429 RATE_LIMITED` with
  `retry_after_seconds`. Success clears the counter; the window expires (no
  permanent lockout). In-process store: correct for a single replica;
  multi-replica deployments must front with gateway IP limiting (see
  `docs/DEPLOYMENT.md`).
- Unknown-email logins run a real Argon2 verification against a dummy hash,
  so timing reveals nothing about account existence; all failures stay
  generic (`INVALID_CREDENTIALS`, no email in logs).

## Intentionally deferred hardening

- Server-side token revocation (denylist/jti tracking) and refresh-token
  rotation: not implemented; short-lived stateless JWTs are the chosen tradeoff.
- Password breach-list (HaveIBeenPwned) checks, MFA (minimal learner/admin
  RBAC is implemented; no finer-grained permissions).
