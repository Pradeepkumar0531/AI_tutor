# Assessment Engine (Prompt 8 — implemented)

Real assessment loop: `Project → Concepts → Learner context → Adaptive
selection → Quiz → Attempts → Evaluation → Assessment → (Prompt 9 Mastery)`.

Home: `app/services/assessment_service.py` + `app/ai/quiz.py`, tables
`quizzes/questions/quiz_questions/question_concepts/quiz_attempts/
question_attempts/assessments` (Prompt 2 domain model, reused unchanged apart
from the additions below), routes `app/api/routes/assessment.py`, UI
`features/quizzes/`.

## Quiz lifecycle (reused enums, no duplicate state)

- Quiz: `DRAFT → READY → ARCHIVED` (`QuizStatus`). Generation is synchronous
  (see below), so only `READY` quizzes are ever persisted here; `DRAFT`
  remains the extension point for a future async variant.
- Progress lives where it belongs: `QuizAttempt` `IN_PROGRESS → COMPLETED /
  ABANDONED` (`AttemptStatus`), `Assessment` `PENDING → COMPLETED`
  (`AssessmentStatus`). Completion is persisted server-side (`completed_at`,
  immutable `Assessment` row) — closing a screen completes nothing.

## Quiz creation (synchronous, bounded, documented)

`POST /projects/{id}/quizzes` validates/authenticates, checks the
`client_request_key` idempotency key, builds the learning context, runs
retrieval + generation with **no open transaction**, then persists
quiz + questions + concept links + placements + `QUIZ_CREATED` event in one
commit. Nothing is persisted unless a READY quiz can be built (retry = POST
again). Per-(concept, type) generation calls keep model usage to
`groups × quiz_max_generation_attempts(2)`; MCQ evaluation never calls a model.

Async decision (§19): generation finishes in seconds (instant under
`TEST_FAKE_AI`), so no Celery job/polling was added. `generation_metadata`
records strategy/counts/model/skipped concepts as the async extension point;
the API contract already supports it (a future variant would return a DRAFT
and finish via worker). No new queue, database, vector store, or framework.

## Adaptive selection strategy

`AssessmentContext` (concepts, recent per-concept outcomes, requested
difficulty/count/types, optional `mastery_estimates`) +
`QuestionSelectionStrategy.select()` → `PlannedSlot`s.
`DefaultQuestionSelectionStrategy`: need = 3×recent-incorrect, 2×unseen,
1×seen-correct, scaled by `(1.5 − mastery)` when Prompt 9 injects estimates;
largest-remainder allocation with a coverage floor; difficulty from the
request/concept (never from correctness — explicitly not wrong=easy);
type round-robin. Pure, deterministic, unit-tested. Bank reuse fills slots
from existing project questions (excluding the bounded served-question
window); generation covers the shortfall.

## Question types, validation, grounding

- `MCQ` (options `[{id, text}]`, `correct_option_id`, `explanation`) and
  `OPEN_ENDED` (`expected_concepts`, `reference_answer`) — matching the DB
  schema (`options` JSONB, `correct_answer` = option id or reference text).
- Generation input per concept: project goal/outcome, concept names, bounded
  RAG evidence (`RetrievalService`, never a second retriever), difficulty,
  type, count. No full PDFs. Evidence-less concepts are skipped; total
  failure → 422 `QUIZ_INSUFFICIENT_EVIDENCE`.
- Validation rejects: wrong types, short/trivial/duplicate prompts, bad
  option counts, duplicate ids/texts, missing/incorrect correct id, empty
  explanation (MCQ), unresolvable concepts, missing reference (open).
  Malformed batches retry within the bound, then the concept is skipped.
- Provenance is app-attached (`question_metadata.provenance`: model, chunk /
  document / material ids, pages from retrieval rows, similarity) — model
  page numbers are never trusted. `QuestionConcept.project_id` + composite
  FKs (`fk_qc_question_in_project`, `fk_qc_concept_in_project`) enforce
  same-project linkage at the database level (migration `0006`).

## Scoring and evaluation

- MCQ: deterministic option-id comparison, no LLM. Score = full points or 0.
- Open-ended: structured Groq evaluation (`correctness` 0–1 clamped,
  understanding/accuracy/relevance enums, concept lists filtered against
  expected concepts so hallucinations never reach feedback/mastery),
  `score = correctness × points`, `is_correct = correctness ≥ 0.6`, partial
  band 0.3–0.6. Bounded retries; failure keeps the persisted answer with a
  safe error and remains retryable (resubmission resumes evaluation).
- Feedback is educational (what was correct/missing, what to review), built
  from question + expected concepts + evidence + learner answer.
- Completion computes totals + concept performance from stored rows only;
  unanswered counts incorrect; pending open answers are evaluated first
  (bounded). Duplicate completion and post-completion answers are 409;
  assessments are immutable (unique `quiz_attempt_id` backstops races).

## Concept performance (Prompt 9 contract)

`ConceptPerformance{concept_id, concept_name, questions_seen, correct_count,
partial_count, incorrect_count, normalized_score, recent[C/P/I ×3]}` and
`AssessmentResult{...totals, score 0–100, concept_results}` — computed at
completion, persisted as the immutable `assessments.concept_results` snapshot
(rebuilt identically on read). No mastery scores, trends, growth, or
recommendations are calculated here.

## Idempotency and failure handling

- Quiz creation: `quizzes.client_request_key` + `uq_quizzes_project_client_key`
  (NULLs distinct) — replays return the original quiz.
- Attempts: resume-IN_PROGRESS (no duplicates on reload/StrictMode).
- Answers: `(quiz_attempt_id, question_id)` unique — identical resubmission
  replays, different answers conflict, completed attempts refuse.
- Open-ended: answer committed before evaluation; evaluation committed after;
  no transaction spans a model call.

## Frontend

`useAssessmentStore` (Zustand) + `QuizSection` (list/create/history) +
`AttemptView` (progress, MCQ radios, open-ended textarea, per-question
feedback, completion) + `AssessmentResultView` (score, concept performance).
Server state is re-fetched (reload-safe); submits disable in flight.

## Tests

Backend `tests/test_assessment.py` (36): strategy, generation paths,
MCQ/open-ended matrices, completion, isolation, routes/learner-safety,
DB isolation. Frontend `src/test/assessment.test.tsx` (11): store + component
flows with the HTTP boundary mocked. E2E `tests/e2e/assessment.spec.ts`:
full journey + adaptive resurfacing on the real stack with `TEST_FAKE_AI`.

## Prompt 9 handoff: AssessmentResult → MasteryService

Completion calls `MasteryService.update_from_assessment(user_id, project_id,
assessment_result)` in a separate transaction after the assessment commits
(mastery faults are logged, never fail completion). The strategy receives
persisted mastery via `mastery_estimates` (`MasteryService` →
`QuestionSelectionStrategy`, read-only, fault-tolerant). See `docs/MASTERY.md`.
