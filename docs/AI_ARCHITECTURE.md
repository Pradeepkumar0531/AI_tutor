# AI Architecture

## Provider boundary (implemented through Prompt 5)

- Domain services must use `AIService`, never raw Groq/Google SDK calls — providers are
  swappable without touching tutor/quiz/recommendation logic.
- Missing keys raise at call time, never at import/startup.

## Knowledge providers (Prompt 6)

- `EmbeddingProvider` protocol (`embed_texts`/`embed_query` via `EmbeddingService`
  in `app/ai/embeddings.py`): order-preserving batches, per-batch timeout,
  transient retry with backoff, strict validation (count, exact 768 width,
  finite floats). Only validated vectors leave the service.
- `GoogleEmbeddingProvider` (`app/ai/google_embeddings.py`): raw calls with
  per-call timeout; SDK errors classified into transient
  (`EmbeddingProviderUnavailable`) vs permanent (`EmbeddingConfigurationError`).
- `ConceptExtractor` protocol (`app/ai/concepts.py`): `GroqConceptExtractor`
  uses `chat_json` (JSON-object mode, 0.2 temperature) with Pydantic-validated
  output; timeouts/connection/rate-limit/5xx surface as retryable
  `AITransientError`, everything else as permanent `ConceptExtractionFailed`.
- Test doubles in `app/ai/fakes.py` (bag-of-words content-derived embeddings —
  same text vectors identically, shared words score higher, disjoint texts
  score near zero — plus keyword concepts): used by unit tests via injection
  and by the E2E worker only when `TEST_FAKE_AI=true` is explicitly set.
  Never in production.
- `FakeChatProvider` tutor mode quotes up to two leading sentences found
  inside `UNTRUSTED SOURCE MATERIAL` blocks (clearly-marked deterministic
  prose otherwise) and returns `TutorStructuredOutput`-shaped JSON; explicitly
  injected chat/embedding providers always win over the settings-based doubles
  so failure injection (timeouts, malformed output) genuinely exercises the
  retry/mapping paths.

## Tutor provider (Prompt 7)

- `AIService.tutor_chat(settings)` resolves the chat provider for
  `TutorService`; `TutorStructuredOutput` (`app/ai/schemas.py`: `answer`,
  `grounded`, `needs_clarification`) is Pydantic-validated, with malformed
  output mapping to permanent `TutorGenerationFailed` (500) and transient
  failures retried with backoff before surfacing 503.
- The model never decides groundedness: `grounded`/`insufficient_evidence`
  are app-computed from retrieval accounting and persisted on the assistant
  message (`tutor_metadata`), so history replay renders identical badges.
- Quiz generation/evaluation (`app/ai/quiz.py`): `QuestionGenerator` builds one
  concept-scoped grounded call per (concept, type) group and returns a validated
  `GeneratedQuestionSet`; `OpenEndedEvaluator` returns a validated
  `OpenEndedEvaluation` (correctness 0–1, understanding/accuracy/relevance enums,
  concept lists, feedback). MCQ evaluation never touches a model — it is a
  deterministic server-side option-id comparison. The application validates
  every AI field, clamps scores, filters concept lists against expected
  concepts, and attaches provenance from retrieval rows; model output can never
  mint scores, leak answers early, or change authorization. Source documents
  and learner answers travel in labeled UNTRUSTED sections only.
- Quiz knobs: `GROQ_MODEL_QUIZ` (default `llama-3.1-8b-instant`),
  `QUIZ_DEFAULT_QUESTION_COUNT` (5), `QUIZ_MAX_QUESTION_COUNT` (20),
  `QUIZ_MAX_GENERATION_ATTEMPTS` (2, shared by generation and evaluation
  retries), `QUIZ_MAX_HISTORY` (50, strategy/exposure window),
  `QUIZ_OPEN_ENDED_MAX_ANSWER_CHARS` (5000), `QUIZ_EVALUATION_MAX_TOKENS`
  (1024), `QUIZ_MAX_RETRIEVED_CHUNKS` (4), `QUIZ_MAX_CONTEXT_CHARS` (6000).
- Tutor knobs: `GROQ_MODEL_TUTOR` (default `llama-3.1-8b-instant`),
  `TUTOR_MAX_HISTORY_MESSAGES` (20), `TUTOR_MAX_HISTORY_CHARS` (8000),
  `TUTOR_MAX_RESPONSE_TOKENS` (1024), `TUTOR_MAX_RETRIEVED_CHUNKS` (6),
  `TUTOR_MAX_CONTEXT_CHARS` (8000), `TUTOR_MAX_CONCEPTS` (10),
  `TUTOR_MAX_RETRIES` (1) — clamped server-side.

## Model configuration (centralized in `Settings`)

- Embedding model: `models/text-embedding-004`, which emits **768-dimensional**
  vectors — matching the fixed `VECTOR(768)` schema. Startup refuses any other
  configured dimension (`ValueError`) so vectors can never silently truncate
  or pad. Related knobs: `GOOGLE_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`,
  `EMBEDDING_BATCH_SIZE`, `EMBEDDING_TIMEOUT_SECONDS`, `EMBEDDING_MAX_RETRIES`.
- Concept model: `GROQ_MODEL_CONCEPTS` (default `llama-3.1-8b-instant`).
- Retrieval knobs: `RAG_TOP_K` (8), `RAG_SIMILARITY_THRESHOLD` (0.3),
  `RAG_MAX_CONTEXT_CHUNKS` (8), `RAG_MAX_CONTEXT_CHARS` (12000) — clamped
  server-side; `CONCEPT_MAX_INPUT_CHARS` (12000), `CONCEPT_MAX_PER_RUN` (20).

## Structured output

- Concept extraction is JSON-mode + Pydantic (`ConceptExtractionResult` in
  `app/ai/schemas.py`): unknown relationship types, self-links, missing
  endpoints, and blank names are dropped server-side; descriptions merge only
  into empty fields; provenance unions by material.

## AI request logging

- `app/ai/observability.py::log_ai_call` emits one structured line per provider
  call: provider, model, operation, latency_ms, status, batch_size,
  input/output tokens **only when reported** (never fabricated), error_type,
  project/material/conversation ids, plus quiz fields where appropriate
  (`quiz_id`, `attempt_id`, `question_type`, `question_count`, `concept_count`
  for `quiz_generate`/`quiz_evaluate`). No keys, prompts, documents, learner
  answers, or reference answers — verified by `test_ai_logging_format`.

- `FakeChatProvider` quiz modes dispatch on the system marker: generation
  returns extractive questions from the delimited evidence (MCQ correct
  answers are always the first option **by test-double contract**, so E2E
  answers deterministically); evaluation scores word overlap with the
  reference, ignoring instruction-override text in the learner answer.
  Backend tests use injected providers for other option layouts and failures.

- Mastery is deterministic application logic, not LLM-generated: no model
  calculates mastery, confidence, trend, or explanations. AI touches
  assessment inputs only (question generation, open-ended evaluation); the
  Mastery Engine consumes validated `AssessmentResult`/`ConceptPerformance`
  records. Tutor prompts may include bounded app-computed mastery estimates
  as depth guidance, never as authority.
- Growth and recommendations are likewise LLM-free: `GrowthService`
  interprets persisted mastery (means, counts, windowed trend comparison);
  `RecommendationService` applies deterministic eligibility/priority rules
  over mastery, recent performance, materials, and goals. No model decides
  eligibility, priority, or wording (fixed templates over structured facts).

- Image extraction involves no AI at all: deterministic PyMuPDF raster
  extraction plus threshold filtering. No vision model, no image embeddings,
  no image OCR beyond the existing page-OCR path; `format_image_references`
  is metadata-only scaffolding for a future multimodal phase (see
  `docs/RAG.md`).

## Failure handling

- Taxonomy in `app/ai/errors.py`: `EmbeddingConfigurationError`,
  `EmbeddingProviderUnavailable`, `EmbeddingDimensionMismatch`,
  `EmbeddingResponseInvalid`, `ConceptExtractionFailed`,
  `KnowledgeProcessingFailed`, `AITransientError` (+ `InsufficientEvidence`
  for explicit require-evidence helpers; search itself returns a flag).
- Taxonomy also includes `TutorGenerationFailed` (malformed tutor output /
  unusable tutor config → 500 via the shared envelope).
- Transient → bounded Celery retries; permanent → FAILED with a user-safe
  message. Knowledge failure never regresses document state (material stays
  READY; embeddings persist for resume).
