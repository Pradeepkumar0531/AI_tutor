# Architecture

## Status: foundation (Prompt 1) + persistence (Prompt 2) + auth/authz (Prompt 3)
+ learning loop (Prompts 4–11) + hardening (Prompt 12) + storage migration
(Prompt 12B) + PRD gap closure (Prompt 12.5: admin, home/analytics, persistent
context, AI observability, evaluation)
+ knowledge/RAG (Prompt 6)
+ spaces/projects (Prompt 4) + materials pipeline (Prompt 5) implemented

## 0. Request path (implemented in Prompt 2)

```mermaid
flowchart LR
    Browser --> Routes[FastAPI routes<br/>no business logic, no SQL]
    Routes --> Services[Service layer<br/>owns transactions]
    Services --> Repos[Repository layer<br/>scoped queries, pagination]
    Repos --> PG[(PostgreSQL + pgvector<br/>Neon)]
    Services --> Events[Event log +<br/>ProcessingJob rows]
    Events --> Worker[Celery worker<br/>claims jobs later]
```

Future components plug into fixed seams without restructuring: Groq/Google via
`app/ai/service.py`, RAG retrieval via `app/rag/` over `document_chunks.embedding`,
document pipeline via `processing_jobs` + `app/jobs/`, uploads via `app/storage/`
(referenced by `materials.storage_key`).

## 1. High-level system architecture (implemented as boundaries)

```mermaid
flowchart LR
    Browser[Browser] --> Vercel[Vercel / static frontend]
    Browser --> API[FastAPI REST /api/v1]
    API --> PG[(Neon PostgreSQL<br/>+ pgvector)]
    API --> Redis[(Upstash Redis<br/>Celery broker)]
    Redis --> Worker[Celery Worker]
    Worker --> OBJ[Neon Object Storage<br/>S3-compatible]
    Worker --> PG
    API --> Groq[Groq LLM]
    API --> Emb[Google Embeddings]
    Worker --> Groq
    Worker --> Emb
```

Boundaries: `app/ai/` (providers), `app/storage/` (Neon/local), `app/jobs/` (Celery),
`app/rag/` (retrieval contracts), `app/documents/` (extraction/chunking contracts).

## 2. Learning domain (IMPLEMENTED in Prompt 2 — 24 tables with later migrations through 0011)

```mermaid
flowchart LR
    User --> Space --> Project --> Material --> Knowledge --> Tutor --> Assessment --> Mastery --> Recommendation
```

## 2b. Assessment → Mastery → Growth → Recommendations loop (Prompts 8–10)

```mermaid
flowchart TD
    Assessment[AssessmentResult<br/>immutable attempt summary]
    MasteryService[MasteryService<br/>deterministic EWMA updates]
    Mastery[(Mastery +<br/>MasteryHistory)]
    GrowthService[GrowthService<br/>interpretation, no new scoring]
    Growth[(Growth rows<br/>per-concept trail)]
    RecService[RecommendationService<br/>deterministic rules]
    Recs[(Recommendations<br/>lifecycle-managed)]
    LearnerAction[Learner action]
    Assessment --> AssessmentResult[AssessmentResult]
    AssessmentResult --> MasteryService
    MasteryService --> Mastery
    Mastery --> GrowthService
    GrowthService --> Growth
    Mastery --> RecService
    Growth -.-> RecService
    RecService --> Recs
    Recs --> LearnerAction
    LearnerAction --> Tutor[Existing Tutor]
    LearnerAction --> Material[Existing materials]
    LearnerAction --> QuizFlow[Existing assessment engine]
    Tutor --> Assessment
    Material --> Assessment
    QuizFlow --> Assessment
```

Real relationships (see docs/DATABASE.md for the ER diagram):

- Users 1—N Spaces; Spaces 1—N Projects (owner denormalized on Project, inherited at creation)
- Projects 1—N Materials → 0/1 Document → N Chunks (VECTOR(768)) + Concepts
- Conversations/Messages per (project, user); Quizzes/Questions/Attempts per project
- Question → Concept → Mastery path via `question_concepts`; Assessments feed MasteryHistory → Mastery → Growth → Recommendations
- Events + ProcessingJobs underpin observability and the async pipeline

## 2c. Analytics + events + dashboard (Prompt 11, read-only layer)

```mermaid
flowchart TD
    Project[Project]
    Project --> Materials[Materials/Documents/Chunks/Images]
    Project --> Knowledge[Concepts + RAG state]
    Project --> Tutor[Conversations/Messages]
    Materials --> Assessment[Assessments/Attempts]
    Knowledge --> Assessment
    Tutor --> Assessment
    Assessment --> AssessmentResult[AssessmentResult]
    AssessmentResult --> MasteryService[MasteryService]
    MasteryService --> Mastery[(Mastery + History)]
    Mastery --> GrowthService[GrowthService]
    GrowthService --> Growth[(Growth rows)]
    Mastery --> RecService[RecommendationService]
    RecService --> Recs[(Recommendations)]
    Assessment --> AnalyticsService[AnalyticsService<br/>COUNT/AVG/GROUP BY reads only]
    Mastery --> AnalyticsService
    Growth -.-> AnalyticsService
    Recs --> AnalyticsService
    Events[Events<br/>audit/activity facts] --> AnalyticsService
    AnalyticsService --> Dashboard[Learner Dashboard<br/>summary + activity + trends]
```

Layer discipline, stated once:

```text
Events        → audit/activity facts (append-only, sanitized payloads)
Analytics     → read-only aggregates over state + events (no new algorithms)
Mastery       → concept-level learning state (source of truth)
Growth        → interpretation of mastery (no new scoring)
Recommendations → actionable next steps (deterministic rules, lifecycle)
```

Analytics never writes learning data, never recomputes scores, and never
exposes private content (conversation bodies, answers, prompts, keys). All
aggregation is SQL-side (`COUNT`/`AVG`/`GROUP BY`, bounded `ORDER BY`,
indexed `project_id`/`user_id` filters); UTC grouping throughout, local-time
conversion at presentation only.

## 3. Async document processing (implemented in Prompt 5)

```mermaid
flowchart TB
    UI[React/Vercel<br/>upload + polling] --> API[FastAPI<br/>validate + store + enqueue]
    API --> PG[(Neon PostgreSQL<br/>Material QUEUED + job)]
    API --> OBJ[Neon Object Storage<br/>or local fs]
    API --> Q[Upstash Redis<br/>or filesystem broker]
    Q --> W[Celery Worker<br/>process_material]
    W --> OBJ
    W --> EXT[PyMuPDF extract]
    EXT --> OCR{PaddleOCR → Tesseract<br/>empty pages only}
    OCR --> NORM[Normalize]
    NORM --> CH[Chunking<br/>page-aware + overlap]
    CH --> PG2[(PostgreSQL<br/>Document + Chunks<br/>embedding NULL)]
    PG2 --> EMB[process_knowledge<br/>embed + concepts]
    EMB --> PG3[(PostgreSQL<br/>vectors + concepts)]
```

Rules that hold: HTTP never extracts (persists + enqueues, returns 201);
the worker needs no request context; one Document per Material (unique);
chunks carry `page_start`/`page_end`; `embedding` stays NULL; no LangChain,
no AI calls in ingestion. Details: `docs/DOCUMENT_PROCESSING.md`.

## 4. Authentication & authorization (implemented in Prompt 3)

```mermaid
flowchart LR
    UI[Login/Register pages] --> Store[Zustand auth store<br/>init/login/register/logout]
    Store --> Client[Axios client<br/>Bearer header + 401 handling]
    Client --> AuthN[POST /auth/*<br/>AuthService + UserRepository]
    Client --> Deps[get_current_user<br/>typ/sub/exp/user checks]
    Deps --> Scope[get_owned_space/project<br/>ownership-chain queries]
    Scope --> Res[Space/Project/Material routes<br/>404 across tenants]
    AuthN --> Evt[USER_* audit events]
```

- Frontend: `tokenStorage.ts` is the only token touchpoint; `RequireAuth` /
  `RedirectIfAuthenticated` guard routes with an explicit `initialized` flag so
  forms are never unmounted mid-submit; `?next=` preserves destinations.
- Backend: `app/auth/` owns policy, JWT (`sub/typ/iat/exp/jti`, 30-min default),
  service transactions, and dependencies. No roles exist (ownership-only model);
  isolation lives in scoped repository queries, proven by the HTTP IDOR matrix
  in `backend/tests/test_auth.py` plus the e2e register→reload→logout→login flow.

## 5. Spaces & Projects (implemented in Prompt 4)

```mermaid
flowchart LR
    Spaces[SpacesPage<br/>grid + search + dialog] --> Detail[SpaceDetailPage<br/>projects in space]
    Detail --> WS[ProjectDetailPage<br/>workspace + future sections]
    WS --> Mats[Materials — Prompt 5]
    WS --> Know[Knowledge/Tutor/Quiz — later]
    Store2[useSpacesStore<br/>useProjectsStore] --> API2[spacesApi/projectsApi<br/>Axios, no N+1 counts]
    API2 --> Svc[ProjectService<br/>update/archive/events]
```

- Routes: `/spaces`, `/spaces/:spaceId`, `/projects`, `/projects/:projectId`
  (protected; placeholders remain for materials/tutor/quizzes/mastery/growth).
- Deletion policy: archive-only (`archived_at`, reversible via `/restore`);
  hard deletes would orphan future Materials/Documents/Chunks/Concepts/Quizzes.
- Counts (`project_count`, `material_count`) come from single GROUP BY queries;
  search is escaped substring `ILIKE` — no search service (semantic search is RAG's job).
- Events: `SPACE_CREATED` (new enum value, migration `0003`) and
  `PROJECT_CREATED` (defined in Prompt 2, first emitted here) fire on creation.

## 6. Knowledge & RAG (implemented in Prompt 6)

```mermaid
flowchart LR
    Q[Query] --> E[Google embedding<br/>validated 768-d] --> V[pgvector &lt;=&gt;<br/>WHERE project_id]
    V --> TH[threshold + top-k] --> C[Bounded context<br/>+ app citations]
```

- `RetrievalService` (`app/rag/retrieval.py`): auth → authorize → embed query →
  SQL-scoped cosine search → threshold/top-k → `RAGContext` with citations and
  an explicit `insufficient_evidence` flag. No Tutor yet — this is the
  foundation Prompt 7 consumes.
- `KnowledgeService` (`app/services/knowledge_service.py`): derived status
  (no new status columns), concept upserts with provenance merge, search
  delegation, reprocess. Background embedding/extraction in
  `app/jobs/knowledge_tasks.py` (atomic claims, per-batch commits, bounded
  retries). Details: `docs/RAG.md`, `docs/AI_ARCHITECTURE.md`.

## 7. PRD gap closure (Prompt 12.5)

```mermaid
flowchart LR
    QuizDone[Quiz completed] --> Mastery[Mastery update]
    Mastery --> Context[LearningContext refresh<br/>rewrite, idempotent]
    Context --> Recs[Recommendations<br/>+ repeated-mistake rule]
    Tutor[Tutor send] --> CtxRead[Bounded context slice<br/>≤1200 chars]
    AI[AI calls] --> Usage[ai_usage ledger<br/>feature/provider/model/latency/tokens/cost]
    Usage --> AdminUI[Admin dashboard]
    Eval[16 curated cases<br/>fake providers, sandbox] --> EvalRuns[evaluation_runs]
    EvalRuns --> AdminUI
    AdminUI --> Ops[overview/users/activity/jobs/health]
```

- RBAC: `users.role` + `require_admin` (server-side) + `ADMIN_EMAILS`
  bootstrap; migration `0010_admin_context_aiusage` (single head preserved).
- Home (`GET /home`) and global analytics (`GET /analytics/summary`) reuse
  `AnalyticsService` aggregates — user-scoped, no new analytics engine.
- Evaluation (`app/evaluation/`): curated cases over real services with
  deterministic doubles; sandbox savepoints rolled back; only outcomes
  persist. Details: `docs/ADMIN.md`, `docs/LEARNING_CONTEXT.md`,
  `docs/AI_EVALUATION.md`, `docs/PRD_TRACEABILITY.md`.
