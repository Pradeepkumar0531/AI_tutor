# API

Base: `/api/v1`. Errors always use `{error: {code, message, details, request_id}}`.
Interactive docs: `/docs`, `/openapi.json` (auth endpoints carry the HTTPBearer
security scheme via the `get_current_user` dependency).

## Auth

| Method & path | Auth | Success | Notes |
|---|---|---|---|
| `POST /auth/register` | no | 201 `{access_token, token_type, expires_in, user}` | `409 RESOURCE_CONFLICT` on duplicate email; `422` on bad email/weak password |
| `POST /auth/login` | no | 200 same shape | `401 INVALID_CREDENTIALS` ("Invalid email or password.") for unknown email, wrong password, or disabled account — identical responses |
| `POST /auth/logout` | Bearer | 200 `{ok: true}` | Writes `USER_LOGOUT` audit; client always drops its token |
| `GET /auth/me` | Bearer | 200 `{id, email, display_name, role, created_at}` | `401 UNAUTHORIZED` without/invalid token; `403 ACCOUNT_DISABLED` for disabled accounts |

## Spaces / projects / materials (ownership-scoped)

All require Bearer auth. Cross-tenant access returns `404 RESOURCE_NOT_FOUND`
with no data disclosure (IDOR protection); missing/invalid tokens return 401.

| Method & path | Notes |
|---|---|
| `POST /spaces` | Create owned space → 201 (emits `SPACE_CREATED`) |
| `GET /spaces?page=&page_size=&search=` | List own active spaces, newest first, with `project_count`; substring name filter |
| `GET /spaces/{id}` | Own active space or 404, with `project_count` |
| `PATCH /spaces/{id}` | Edit `name`/`description` only (blank names → 400) |
| `DELETE /spaces/{id}` | Archive (sets `archived_at`, reversible) → 200 |
| `POST /spaces/{id}/restore` | Un-archive → 200 |
| `POST /projects` | `{space_id, name, ...}`; 404 unless the space is yours (owner inherited); emits `PROJECT_CREATED` |
| `GET /projects?space_id=&page=&page_size=&search=` | List own active projects (optionally within one owned space), with `material_count`; filtering by another user's space yields `[]`, never its contents |
| `GET /projects/{id}` | Own active project or 404, with `material_count` |
| `PATCH /projects/{id}` | Edit `name`/`description`/`learning_goal`/`target_outcome`/`difficulty` only — never owner/space/ids/metrics |
| `DELETE /projects/{id}` | Archive (reversible, children preserved) → 200 |
| `POST /projects/{id}/restore` | Un-archive → 200 |
| `GET /projects/{id}/materials` | Paginated materials with `page_count`/`chunk_count`, optional `?status=` filter |

## Materials / documents (ownership-scoped, Bearer required)

Upload is `multipart/form-data` with a `file` part (PDF only) and optional
`title` form field. Limits: 25 MB default (`MAX_UPLOAD_BYTES`), validated by
extension + declared type + `%PDF-` magic bytes.

| Method & path | Notes |
|---|---|
| `POST /projects/{id}/materials` | Upload → 201 `MaterialRead` (`QUEUED`); enqueues `process_material` after commit; broker outage still returns 201 with job QUEUED |
| `GET /projects/{id}/materials/{mid}/images?page=&page_size=` | Paginated extracted-image metadata (id, document, page, index, dimensions, MIME, size — never storage keys or hashes) |
| `GET /projects/{id}/materials/{mid}/images/{iid}` | One image's metadata or 404 |
| `GET /projects/{id}/materials/{mid}/images/{iid}/content` | Image bytes with native MIME through the authenticated API (bucket stays private; no signed URLs); missing binary → 404, logged server-side |

## Knowledge / RAG (ownership-scoped, Bearer required)

| Method & path | Notes |
|---|---|
| `GET /projects/{id}/knowledge` | Derived status `PENDING/PROCESSING/READY/FAILED` + totals (chunks, embedded, concepts, ready materials) |
| `GET /projects/{id}/concepts?page=&page_size=` | Paginated project concepts (name, description only — no internals) |
| `GET /projects/{id}/concepts/{cid}` | Concept + linked materials, supporting-chunk count, pages |
| `POST /projects/{id}/knowledge/search` | Body `{query, top_k?, threshold?, material_ids?}` → `{query, results, citations, context, insufficient_evidence}`; 422 on blank query; never returns embeddings or storage keys |
| `POST /projects/{id}/materials/{mid}/reprocess-knowledge` | Reset one material's embeddings + requeue → 202; 409 while a knowledge job is live |
| `GET /projects/{id}/materials/{mid}` | Detail: status, safe error, document summary, chunk count |
| `GET /projects/{id}/materials/{mid}/document` | Document metadata + counts; 404 until READY |
| `GET /projects/{id}/materials/{mid}/document/chunks?page=` | DB-paginated chunks in index order, embeddings excluded |
| `POST /projects/{id}/materials/{mid}/reprocess` | `FAILED` → `QUEUED` only; 409 otherwise or when a job is pending |
| `DELETE /projects/{id}/materials/{mid}` | Archive (storage + document + chunks retained for restore) |
| `POST /projects/{id}/materials/{mid}/restore` | Un-archive |

Processing states: `QUEUED → PROCESSING → READY`, or `FAILED` with a
user-safe `processing_error` (diagnostics stay in server logs). Responses never
contain storage keys, paths, credentials, or stack traces.

## Tutor (ownership-scoped, Bearer required)

Conversations live under `user → project → conversation`; cross-tenant access
returns the same 404 as a missing project. `MessageRead` carries app-computed
`grounded` / `insufficient_evidence` flags (persisted server-side, replayed for
history) plus citations — never model prose parsing, prompts, embeddings, or
provider payloads.

| Method & path | Notes |
|---|---|
| `POST /projects/{id}/conversations` | Body `{title?}` → 201 `ConversationRead` + `CONVERSATION_CREATED` event |
| `GET /projects/{id}/conversations` | Newest-first `ConversationRead[]` |
| `GET /projects/{id}/conversations/{cid}` | One conversation or 404 |
| `GET /projects/{id}/conversations/{cid}/messages?limit=` | Chronological `Page[MessageRead]` (limit 1–200, default 100) |
| `POST /projects/{id}/conversations/{cid}/messages` | Body `{content (1–4000 chars, non-blank), request_key? (≤64)}` → `{conversation_id, message, citations, grounded, insufficient_evidence}`; same `request_key` replays the persisted exchange instead of duplicating; transient provider failure → 503 after bounded retries, malformed output/missing key → 500 (`TUTOR_GENERATION_FAILED`); unsupported actions refused before any model call |

## Assessment / quizzes (ownership-scoped, Bearer required)

Every endpoint enforces `user → project → quiz → attempt → question`. Cross-tenant
access returns the same 404 as a missing project. Pre-answer payloads are learner-safe
(no correct answers, reference answers, or evaluator internals); post-answer payloads
reveal feedback only for the answered question.

| Method & path | Notes |
|---|---|
| `POST /projects/{id}/quizzes` | Body `{question_count? (1–20, default 5), difficulty?, focus_concepts?, question_types? (MCQ/OPEN_ENDED), title?, client_request_key?}` → 201 READY quiz with learner-safe questions (200 replay for a repeated `client_request_key`); 422 when no concepts or no project evidence; 503/500 on bounded generation failure; nothing persisted on failure |
| `GET /projects/{id}/quizzes` | Newest-first quizzes with question counts |
| `GET /projects/{id}/quizzes/{qid}` | Quiz + learner-safe questions (concept labels, source material/pages — never answers) |
| `POST /projects/{id}/quizzes/{qid}/attempts` | 201 new / 200 resume IN_PROGRESS attempt + questions with own answer states; 409 unless quiz READY with questions |
| `GET /projects/{id}/attempts/{aid}` | Attempt + questions with own answers/feedback (reload-safe resume) |
| `POST /projects/{id}/attempts/{aid}/answers` | Body `{question_id, answer}` → deterministic MCQ grading or structured open-ended evaluation; identical resubmission replays, different answer 409s, completed attempts 409 |
| `POST /projects/{id}/attempts/{aid}/complete` | Server-computed totals + per-concept results → persisted immutable Assessment; duplicate 409 |
| `GET /projects/{id}/assessments` | Newest-first assessment summaries (result history) |
| `GET /projects/{id}/assessments/{aid}` | Full assessment result incl. `concept_results` for Prompt 9 |

## Growth / recommendations (ownership-scoped, Bearer required)

Growth is computed live from persisted Mastery rows (no separate scoring
algorithm); recommendations are generated deterministically server-side on
assessment completion. No endpoint writes mastery or growth directly.

| Method & path | Notes |
|---|---|
| `GET /projects/{id}/growth` | Project aggregate: status (`IMPROVING/STABLE/REQUIRING_ATTENTION`), `has_evidence`, overall mastery/confidence, per-status concept counts, assessment/question counts, per-concept breakdown; cold start → `STABLE` + `has_evidence: false` |
| `GET /projects/{id}/growth/history?limit=` | Assessment-score trajectory (chronological, bounded) for the chart; no fabricated points |
| `GET /projects/{id}/recommendations?page=&page_size=` | Active recommendations newest-priority-first with title/reason/backend-confirmed `actions`/priority/concept/material |
| `GET /projects/{id}/recommendations/{rid}` | One recommendation or 404 |
| `POST /projects/{id}/recommendations/{rid}/complete` | `ACTIVE` → `COMPLETED` (+ timestamp); non-active → 409 |
| `POST /projects/{id}/recommendations/{rid}/dismiss` | `ACTIVE` → `DISMISSED`; non-active → 409 |

## Analytics / events (ownership-scoped, Bearer required)

Read-only aggregation over persisted state + the event activity stream. No
endpoint writes learning data; every number comes from domain tables, the
Growth/Mastery/Recommendation services, or events — never fabricated.

| Method & path | Notes |
|---|---|
| `GET /projects/{id}/analytics/dashboard` | One-call summary: material/document/page/chunk/image/concept counts, assessment + question breakdown, average score, overall mastery/confidence/growth status (null when no evidence), active recommendations, tutor conversations/messages, last activity, `has_learning_evidence` |
| `GET /projects/{id}/analytics/activity?range=&limit=&event_type=` | Curated timeline (milestones with human summaries + resource ids; pipeline internals excluded); `range` in `7d/30d/90d/all`, limit 1–100 |
| `GET /projects/{id}/analytics/activity-by-day?range=` | Contiguous UTC day counts (zero-filled) for bounded ranges; sparse points for `all` |
| `GET /projects/{id}/analytics/mastery-trend?limit=` | Assessment-score trajectory reusing the growth history contract |
| `GET /projects/{id}/events?page=&page_size=&event_type=&since=&until=` | Tenant-scoped feed, newest first, sanitized metadata; unknown types → 422 |
| `GET /analytics/summary` | Cross-project aggregates for the caller only (counts, mastery avg, attention, active recs, recent projects) |
| `GET /home` | Continue-learning home: most recent project + derived next action, recent projects, honest progress, attention, recommended action |

## Admin (admin role required, Bearer required)

Server-side `require_admin` on every route; learners 403, anonymous 401.
Paginated (`limit` ≤ 100), secret-free (no hashes, tokens, keys, embeddings).

| Method & path | Notes |
|---|---|
| `GET /admin/overview` | COUNT aggregates + jobs GROUP BY status |
| `GET /admin/users` | Paginated users (role, active, login) |
| `GET /admin/users/{id}` | Learning journey: spaces, projects, assessments, mastery snapshot, recs, AI usage + cost, recent events |
| `GET /admin/activity?user_id=&space_id=&project_id=&event_type=&since=&until=` | Platform events, server-filtered |
| `GET /admin/jobs?status=` | Job type/status/attempts/timestamps + 300-char safe errors |
| `GET /admin/health` | API/database/AI/storage/queue presence — booleans only, never secrets |
| `GET /admin/ai-usage/summary`, `GET /admin/ai-usage` | Per (feature, provider, model) aggregates + recent rows |
| `GET /admin/evaluations/summary`, `GET /admin/evaluations` | Last run, per-category totals, recent failures |
| `POST /admin/evaluations/run` | Runs the 16-case suite sandboxed (rolls back) and persists outcomes |

## Health (public)

`GET /health`, `GET /health/ready` — unchanged from Prompt 1.

## Status semantics

- 401 `UNAUTHORIZED`: missing/invalid/expired/mistyped token, unknown subject.
- 403 `ACCOUNT_DISABLED`: valid token, disabled account.
- 403 `FORBIDDEN`: authenticated non-admin on `/admin/*` (server-side RBAC).
- 404 `RESOURCE_NOT_FOUND`: not yours or doesn't exist (preferred over 403 for
  resource reads to avoid existence leaks).
- 409 `RESOURCE_CONFLICT`: duplicate registration.
- 422 `VALIDATION_ERROR`: schema/policy violations (sanitized details).

## Hardening boundary (implemented Prompt 12)

Login rate limiting is implemented (per-email sliding window → 429); the
remaining seam is gateway-level IP limiting (Upstash/edge) for multi-replica
deployments, checked in `AuthService.login` before
password verification, returning `429` with `Retry-After`. Nothing is faked in
the meantime — brute-force mitigation currently relies on Argon2id cost +
generic failure messages + short token lifetimes.
