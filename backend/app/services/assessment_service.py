"""Adaptive Quiz & Assessment Engine (Prompt 8).

Pipeline: project authorization -> learning/concept context -> adaptive
concept selection (``QuestionSelectionStrategy``) -> bank reuse + grounded AI
generation -> validation -> quiz persistence -> attempts -> deterministic MCQ
evaluation / structured open-ended evaluation -> server-side completion ->
immutable ``Assessment`` with per-concept results for Prompt 9's Mastery
engine.

Deliberate non-goals: final mastery scores, growth, recommendations (Prompt 9+).

Lifecycle reuse (no duplicate state): Quiz ``DRAFT`` (only ever persisted as
``READY`` here — generation is synchronous, see below) → ``READY`` →
``ARCHIVED``; progress lives on QuizAttempt ``IN_PROGRESS`` → ``COMPLETED`` /
``ABANDONED``; Assessment ``PENDING`` → ``COMPLETED``.

Synchronous generation decision (§19): with bounded per-concept calls the
whole generation finishes in seconds (instant under ``TEST_FAKE_AI``), so
``POST /quizzes`` returns a READY quiz directly — no Celery job, no polling,
no browser-open requirement beyond the single request. ``generation_metadata``
records the strategy/counts/model as the extension point: a future async
variant can persist DRAFT first and finish via worker without changing the
API contract.
"""

from __future__ import annotations

import abc
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.errors import (
    AITransientError,
    QuizEvaluationFailed,
    QuizGenerationFailed,
    QuizInsufficientEvidence,
)
from app.ai.observability import log_ai_call
from app.core.config import Settings, get_settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.models.assessment import (
    Assessment,
    Question,
    QuestionAttempt,
    Quiz,
    QuizAttempt,
    QuizQuestion,
)
from app.models.enums import (
    AssessmentStatus,
    AttemptStatus,
    Difficulty,
    EventType,
    QuestionType,
    QuizStatus,
)
from app.models.knowledge import Concept
from app.models.learning import Project
from app.models.mixins import utcnow
from app.models.users import User
from app.rag.retrieval import format_chunks_for_prompt
from app.repositories.assessments import (
    AssessmentRepository,
    AttemptRepository,
    QuestionRepository,
    QuizRepository,
)
from app.repositories.intelligence import EventRepository
from app.repositories.knowledge import ConceptRepository
from app.repositories.projects import ProjectRepository
from app.services.assessment_contracts import (
    CORRECT_AT,
    PARTIAL_MIN,
    AssessmentResult,
    ConceptPerformance,
)
from app.services.base import BaseService, transactional

log = logging.getLogger("app.services.assessment")

MAX_PROMPT_CHARS = 4000
MCQ_MIN_OPTIONS = 2
MCQ_MAX_OPTIONS = 6
MIN_PROMPT_CHARS = 15
_OPTION_ID_RE = re.compile(r"^[A-Z0-9]{1,8}$")

# Trivial prompts that can never become questions (case-insensitive).
_TRIVIAL_RE = re.compile(r"^(what|why|how|explain|describe|define)\s*\??$")


def _normalize_prompt(prompt: str) -> str:
    return re.sub(r"\s+", " ", prompt.strip().lower())


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _normalize_difficulty(value: object) -> Difficulty:
    try:
        return Difficulty(str(value).strip().upper())
    except ValueError:
        return Difficulty.MEDIUM


# ------------------------------------------------------------ Prompt 9 contract
# (Defined in assessment_contracts so MasteryService can consume the result
# without a circular import; re-exported here for compatibility.)


# ------------------------------------------------------------ selection strategy


@dataclass
class PlannedSlot:
    concept_id: uuid.UUID
    difficulty: Difficulty
    question_type: QuestionType


@dataclass
class AssessmentContext:
    """Everything the strategy may consider. ``mastery_estimates`` is the
    Prompt 9 injection point (concept_id -> 0-1); always None in Prompt 8 —
    the strategy falls back to raw assessment history, never fabricated
    mastery scores."""

    concepts: list[Concept]
    outcomes: dict[uuid.UUID, list[tuple[bool | None, float | None]]] = field(default_factory=dict)
    requested_difficulty: Difficulty | None = None
    question_count: int = 5
    question_types: list[QuestionType] = field(
        default_factory=lambda: [QuestionType.MCQ, QuestionType.OPEN_ENDED]
    )
    mastery_estimates: dict[uuid.UUID, float] | None = None


class QuestionSelectionStrategy(abc.ABC):
    """Deterministic concept-slot planner. Prompt 9 can subclass or replace
    this to inject real mastery estimates; the quiz pipeline is unchanged."""

    @abc.abstractmethod
    def select(self, context: AssessmentContext) -> list[PlannedSlot]:
        """Return exactly ``context.question_count`` slots (or fewer when no
        concepts exist). Pure function: no I/O, no randomness."""


class DefaultQuestionSelectionStrategy(QuestionSelectionStrategy):
    """Coverage first, then mistakes — explicitly NOT 'wrong = easy'.

    Need score per concept: recent incorrect answers weigh most (3), unseen
    concepts next (2), seen-but-correct least (1); difficulty is NEVER derived
    from correctness. Slots are allocated by largest remainder over need, so a
    follow-up quiz after a mixed attempt emphasizes missed concepts while
    keeping coverage. Optional mastery estimates scale need by
    ``(1.5 - mastery)`` instead of replacing history.
    """

    INCORRECT_WEIGHT = 3.0
    UNSEEN_WEIGHT = 2.0
    SEEN_WEIGHT = 1.0

    def select(self, context: AssessmentContext) -> list[PlannedSlot]:
        concepts = list(context.concepts)
        if not concepts or context.question_count <= 0:
            return []
        needs = {c.id: self._need(c.id, context) for c in concepts}
        total_need = sum(needs.values()) or 1.0
        # Largest-remainder allocation keeps counts exact and deterministic
        # (ties broken by concept name, never by dict order).
        ordered = sorted(concepts, key=lambda c: (c.name.lower(), str(c.id)))
        exact = {c.id: needs[c.id] / total_need * context.question_count for c in ordered}
        counts = {c.id: int(exact[c.id]) for c in ordered}
        remainder = context.question_count - sum(counts.values())
        leftovers = sorted(ordered, key=lambda c: exact[c.id] - counts[c.id], reverse=True)
        for concept in leftovers[: max(remainder, 0)]:
            counts[concept.id] += 1
        # Guarantee every concept appears when slots allow (coverage floor).
        if context.question_count >= len(ordered):
            for concept in ordered:
                counts[concept.id] = max(counts[concept.id], 1)
            overflow = sum(counts.values()) - context.question_count
            for concept in sorted(ordered, key=lambda c: (needs[c.id], c.name.lower(), str(c.id))):
                while overflow > 0 and counts[concept.id] > 1:
                    counts[concept.id] -= 1
                    overflow -= 1
        slots: list[PlannedSlot] = []
        types = list(context.question_types) or [QuestionType.MCQ]
        type_index = 0
        for concept in ordered:
            difficulty = context.requested_difficulty or (concept.difficulty or Difficulty.MEDIUM)
            for _ in range(counts[concept.id]):
                slots.append(
                    PlannedSlot(
                        concept_id=concept.id,
                        difficulty=difficulty,
                        question_type=types[type_index % len(types)],
                    )
                )
                type_index += 1
        return slots[: context.question_count]

    def _need(self, concept_id: uuid.UUID, context: AssessmentContext) -> float:
        outcomes = context.outcomes.get(concept_id, [])
        incorrect = sum(1 for correct, _ in outcomes if correct is False)
        if incorrect:
            base = incorrect * self.INCORRECT_WEIGHT
        elif not outcomes:
            base = self.UNSEEN_WEIGHT
        else:
            base = self.SEEN_WEIGHT
        if context.mastery_estimates:
            mastery = context.mastery_estimates.get(concept_id)
            if mastery is not None:
                return base * (1.5 - min(max(mastery, 0.0), 1.0))
        return base


# ------------------------------------------------------------ generation record


@dataclass
class PreparedQuestion:
    """Validated, app-owned question record ready to persist. Concept ids are
    resolved in-project UUIDs; provenance chunks come from retrieval rows —
    never from model output."""

    type: QuestionType
    prompt: str
    options: list[dict] | None
    correct_option_id: str | None
    explanation: str | None
    expected_concepts: list[str]
    reference_answer: str | None
    concept_ids: list[uuid.UUID]
    difficulty: Difficulty
    provenance: dict


class AssessmentService(BaseService):
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        ai_service=None,  # AIService; untyped to avoid import weight here
        selection_strategy: QuestionSelectionStrategy | None = None,
    ) -> None:
        super().__init__(session)
        self.settings = settings or get_settings()
        self.ai_service = ai_service
        self.selection_strategy = selection_strategy or DefaultQuestionSelectionStrategy()
        self.projects = ProjectRepository(session)
        self.concepts = ConceptRepository(session)
        self.quizzes = QuizRepository(session)
        self.questions = QuestionRepository(session)
        self.attempts = AttemptRepository(session)
        self.assessments = AssessmentRepository(session)
        self.events = EventRepository(session)

    def _ai(self):
        if self.ai_service is None:
            from app.ai.service import ai_service

            return ai_service
        return self.ai_service

    # ------------------------------------------------------------ quiz creation

    async def create_quiz(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        question_count: int = 5,
        difficulty: Difficulty | None = None,
        focus_concepts: list[uuid.UUID] | None = None,
        question_types: list[QuestionType] | None = None,
        title: str | None = None,
        client_request_key: str | None = None,
    ) -> tuple[Quiz, bool]:
        """Generate and persist a READY quiz synchronously (see module notes).

        Returns (quiz, created): idempotent replays return the original quiz
        with created=False. Nothing is persisted unless a READY quiz can be
        built — failures leave no misleading rows; retry by POSTing again.
        """
        from app.rag.retrieval import RetrievalService

        settings = self.settings
        count = min(
            max(question_count or settings.quiz_default_question_count, 1),
            settings.quiz_max_question_count,
        )
        types = self._normalize_types(question_types)
        raw_key = client_request_key.strip() if client_request_key else None
        key = raw_key or None
        if key and len(key) > 64:
            raise BadRequestError("client_request_key must be 64 characters or fewer.")
        if self.session.get(User, user_id) is None:
            raise NotFoundError("User not found.")
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")

        if key:
            existing = self.quizzes.find_by_client_key(project.id, key)
            if existing is not None:
                return existing, False

        concepts = self._resolve_concepts(project, focus_concepts)
        if not concepts:
            raise QuizInsufficientEvidence(
                "This project has no concepts to assess yet. "
                "Upload material and wait for knowledge processing first."
            )

        context = self._build_context(
            project=project,
            user_id=user_id,
            concepts=concepts,
            requested_difficulty=difficulty,
            question_count=count,
            question_types=types,
        )
        slots = self.selection_strategy.select(context)
        if not slots:
            raise QuizInsufficientEvidence("No assessable concepts found for this quiz.")

        embedding_service = self._ai().embedding_service(settings)
        retrieval = RetrievalService(self.session, embedding_service, settings)
        generator = self._ai().question_generator(settings)
        prepared = await self._fill_slots(
            project=project,
            user_id=user_id,
            concepts={c.id: c for c in concepts},
            slots=slots,
            retrieval=retrieval,
            generator=generator,
        )
        if not prepared:
            raise QuizInsufficientEvidence(
                "None of the selected concepts had enough project evidence to "
                "build grounded questions. Try uploading material that covers "
                "these topics."
            )
        return self._persist_quiz(
            user_id=user_id,
            project=project,
            prepared=prepared,
            title=(title.strip() if title and title.strip() else "Untitled quiz"),
            difficulty=difficulty,
            client_request_key=key,
            concept_ids={c.id for c in concepts},
        ), True

    def list_quizzes(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> list[Quiz]:
        project = self._owned_project(user_id, project_id)
        return self.quizzes.list_for_project(project.id)

    def get_quiz(self, *, user_id: uuid.UUID, project_id: uuid.UUID, quiz_id: uuid.UUID) -> Quiz:
        project = self._owned_project(user_id, project_id)
        quiz = self.quizzes.get_for_project(quiz_id, project.id)
        if quiz is None:
            raise NotFoundError("Quiz not found.")
        return quiz

    def quiz_question_counts(self, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
        return self.quizzes.question_counts(project_id)

    def attempt_detail_view(self, attempt: QuizAttempt) -> dict:
        """Attempt + ordered questions, each with the learner's own answer
        state. Unanswered questions are learner-safe; answered ones additionally
        carry feedback (and, for MCQ, the correct option — nothing leaks
        before submission)."""
        answers = {row.question_id: row for row in self.attempts.answers_for_attempt(attempt.id)}
        questions = []
        for placement in self.quizzes.ordered_questions(attempt.quiz_id):
            question = self.session.get(Question, placement.question_id)
            if question is None:
                continue
            view = self._learner_question(
                question, position=placement.position, points=placement.points
            )
            row = answers.get(question.id)
            if row is None or not (row.answer or "").strip():
                view["answer"] = {
                    "submitted": None,
                    "is_correct": None,
                    "score": None,
                    "feedback": None,
                    "correct_option_id": None,
                    "evaluation": None,
                }
            else:
                view["answer"] = {
                    "submitted": row.answer,
                    "is_correct": row.is_correct,
                    "score": row.score,
                    "feedback": row.feedback,
                    "correct_option_id": (
                        question.correct_answer if question.type == QuestionType.MCQ else None
                    ),
                    "evaluation": row.evaluation,
                }
            questions.append(view)
        return {"attempt": attempt, "questions": questions}

    # ------------------------------------------------------------ attempts

    async def start_attempt(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, quiz_id: uuid.UUID
    ) -> tuple[QuizAttempt, bool]:
        """Start or resume the user's IN_PROGRESS attempt (reload/StrictMode
        safe: never duplicates). The quiz must be READY with questions."""
        project = self._owned_project(user_id, project_id)
        quiz = self.quizzes.get_for_project(quiz_id, project.id)
        if quiz is None:
            raise NotFoundError("Quiz not found.")
        if quiz.status != QuizStatus.READY:
            raise ConflictError("This quiz is not ready to attempt.")
        placements = self.quizzes.ordered_questions(quiz.id)
        if not placements:
            raise ConflictError("This quiz has no questions yet.")
        existing = self.attempts.find_active(quiz.id, user_id)
        if existing is not None:
            return existing, False
        attempt = self._start_attempt_row(
            user_id=user_id, project=project, quiz=quiz, total=len(placements)
        )
        return attempt, True

    def get_attempt(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> QuizAttempt:
        project = self._owned_project(user_id, project_id)
        attempt = self.attempts.get_for_project(attempt_id, project.id, user_id)
        if attempt is None:
            raise NotFoundError("Attempt not found.")
        return attempt

    # ------------------------------------------------------------ internals

    def _owned_project(self, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        if self.session.get(User, user_id) is None:
            raise NotFoundError("User not found.")
        project = self.projects.get_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project not found.")
        return project

    @staticmethod
    def _normalize_types(
        question_types: list[QuestionType] | None,
    ) -> list[QuestionType]:
        if not question_types:
            return [QuestionType.MCQ, QuestionType.OPEN_ENDED]
        seen: list[QuestionType] = []
        for item in question_types:
            try:
                qtype = item if isinstance(item, QuestionType) else QuestionType(str(item).upper())
            except ValueError as e:
                raise BadRequestError(f"Unsupported question type: {item}.") from e
            if qtype not in seen:
                seen.append(qtype)
        if not seen:
            raise BadRequestError("At least one question type is required.")
        return seen

    def _resolve_concepts(
        self, project: Project, focus_concepts: list[uuid.UUID] | None
    ) -> list[Concept]:
        if not focus_concepts:
            return self.concepts.all_for_project(project.id)
        resolved: list[Concept] = []
        for concept_id in focus_concepts:
            concept = self.concepts.get_for_project(concept_id, project.id)
            if concept is None:
                raise NotFoundError("Concept not found.")
            if concept.id not in {c.id for c in resolved}:
                resolved.append(concept)
        return resolved

    def _build_context(
        self,
        *,
        project: Project,
        user_id: uuid.UUID,
        concepts: list[Concept],
        requested_difficulty: Difficulty | None,
        question_count: int,
        question_types: list[QuestionType],
    ) -> AssessmentContext:
        settings = self.settings
        outcomes: dict[uuid.UUID, list[tuple[bool | None, float | None]]] = {}
        for concept_id, is_correct, score in self.attempts.recent_concept_outcomes(
            project.id, user_id, limit=settings.quiz_max_history
        ):
            outcomes.setdefault(concept_id, []).append((is_correct, score))
        return AssessmentContext(
            concepts=list(concepts),
            outcomes=outcomes,
            requested_difficulty=requested_difficulty,
            question_count=question_count,
            question_types=list(question_types),
            mastery_estimates=self._mastery_estimates(
                user_id=user_id,
                project=project,
                concept_ids=[c.id for c in concepts],
            ),
        )

    def _mastery_estimates(
        self, *, user_id: uuid.UUID, project: Project, concept_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, float] | None:
        """Real persisted mastery for the candidate concepts (Prompt 9 wire).
        Read-only: a lookup failure degrades to history-only selection rather
        than failing quiz creation. Returns None when nothing is known."""
        try:
            from app.services.mastery_service import MasteryService

            estimates = MasteryService(self.session, settings=self.settings).scores_for_concepts(
                user_id=user_id, project_id=project.id, concept_ids=concept_ids
            )
            return estimates or None
        except Exception as e:  # noqa: BLE001 - selection must survive mastery faults
            log.warning("mastery estimates unavailable project=%s err=%s", project.id, e)
            return None

    # ------------------------------------------------------------ generation

    async def _fill_slots(
        self,
        *,
        project: Project,
        user_id: uuid.UUID,
        concepts: dict[uuid.UUID, Concept],
        slots: list[PlannedSlot],
        retrieval,
        generator,
    ) -> list[PreparedQuestion]:
        """Bank reuse first, grounded generation for the shortfall.

        Existing project questions linked to a slot's concept are reused when
        the learner has not seen them recently (bounded exposure window);
        otherwise one grounded generation call per (concept, type) group
        fills the rest. No database transaction is held during retrieval or
        model calls — persistence happens once, in ``_persist_quiz``.
        """
        served = await self._served_question_ids(project.id, user_id)
        kept: list[PreparedQuestion] = []
        kept_prompts: set[str] = set()

        # Group slots to bound model calls: one call per (concept, type).
        groups: dict[tuple[uuid.UUID, QuestionType], list[PlannedSlot]] = {}
        for slot in slots:
            groups.setdefault((slot.concept_id, slot.question_type), []).append(slot)

        for (concept_id, qtype), group in groups.items():
            concept = concepts.get(concept_id)
            if concept is None:
                continue
            needed = len(group)
            reused = self._reuse_bank(
                concept_id=concept_id,
                project_id=project.id,
                exclude_ids=served,
                needed=needed,
                kept_prompts=kept_prompts,
            )
            kept.extend(reused)
            remaining = needed - len(reused)
            if remaining <= 0:
                continue
            generated = await self._generate_for_concept(
                project=project,
                user_id=user_id,
                concept=concept,
                question_type=qtype,
                count=remaining,
                difficulty=group[0].difficulty,
                retrieval=retrieval,
                generator=generator,
                kept_prompts=kept_prompts,
            )
            kept.extend(generated)
        return kept

    async def _served_question_ids(
        self, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> set[uuid.UUID]:
        """Bounded exposure window: question ids from the learner's recent
        attempts in this project (any status)."""
        from app.models.assessment import QuestionAttempt as QuestionAttemptModel

        limit = self.settings.quiz_max_history
        rows = self.session.execute(
            sa.select(QuestionAttemptModel.question_id)
            .join(QuizAttempt, QuizAttempt.id == QuestionAttemptModel.quiz_attempt_id)
            .where(QuizAttempt.project_id == project_id, QuizAttempt.user_id == user_id)
            .order_by(QuestionAttemptModel.answered_at.desc(), QuestionAttemptModel.id.desc())
            .limit(min(max(limit, 1), 200))
        )
        return {row[0] for row in rows}

    def _reuse_bank(
        self,
        *,
        concept_id: uuid.UUID,
        project_id: uuid.UUID,
        exclude_ids: set[uuid.UUID],
        needed: int,
        kept_prompts: set[str],
    ) -> list[PreparedQuestion]:
        """Reuse existing project questions for a concept (no AI cost, no
        repetition). Returns app-owned records in the same shape as
        validated generation output."""
        reused: list[PreparedQuestion] = []
        for question in self.questions.candidates_for_concept(
            concept_id, project_id, exclude_ids=exclude_ids, limit=needed * 2
        ):
            if len(reused) >= needed:
                break
            normalized = _normalize_prompt(question.prompt)
            if normalized in kept_prompts:
                continue
            links = self.questions.concepts_for_question(question.id)
            concept_ids = [link.concept_id for link, _ in links]
            if concept_id not in concept_ids:
                continue
            options = self._learner_options(question)
            reused.append(
                PreparedQuestion(
                    type=question.type,
                    prompt=question.prompt,
                    options=(
                        [{"id": o["id"], "text": o["text"]} for o in options]
                        if question.type == QuestionType.MCQ
                        else None
                    ),
                    correct_option_id=(
                        question.correct_answer if question.type == QuestionType.MCQ else None
                    ),
                    explanation=question.explanation,
                    expected_concepts=self._expected_concepts(question),
                    reference_answer=question.correct_answer
                    if question.type == QuestionType.OPEN_ENDED
                    else None,
                    concept_ids=concept_ids,
                    difficulty=question.difficulty or Difficulty.MEDIUM,
                    provenance=dict((question.question_metadata or {}).get("provenance", {})),
                )
            )
            kept_prompts.add(normalized)
        return reused

    async def _generate_for_concept(
        self,
        *,
        project: Project,
        user_id: uuid.UUID,
        concept: Concept,
        question_type: QuestionType,
        count: int,
        difficulty: Difficulty,
        retrieval,
        generator,
        kept_prompts: set[str],
    ) -> list[PreparedQuestion]:
        """One concept, one evidence scope, bounded generation attempts.
        Concepts without retrievable evidence are skipped (never fabricated);
        malformed model output is retried within ``quiz_max_generation_attempts``
        and then the concept is skipped — never endlessly retried."""
        settings = self.settings
        query = (
            concept.name
            if not concept.description
            else f"{concept.name}: {concept.description[:300]}"
        )
        try:
            result = await retrieval.search(
                user_id=user_id,
                project_id=project.id,
                query=query,
                top_k=settings.quiz_max_retrieved_chunks,
                max_chunks=settings.quiz_max_retrieved_chunks,
                max_chars=settings.quiz_max_context_chars,
            )
        except NotFoundError:
            raise
        if result.insufficient_evidence or not result.results:
            log.info(
                "quiz generation skipped concept without evidence concept=%s project=%s",
                concept.id,
                project.id,
            )
            return []
        evidence_text = format_chunks_for_prompt(result.results)
        provenance_chunks = [
            {
                "chunk_id": str(c.chunk_id),
                "document_id": str(c.document_id),
                "material_id": str(c.material_id),
                "material_name": c.material_name,
                "page_start": c.page_start,
                "page_end": c.page_end,
            }
            for c in result.citations
        ]
        project_concepts = {c.id: c for c in self.concepts.all_for_project(project.id)}
        prepared: list[PreparedQuestion] = []
        attempts = min(max(settings.quiz_max_generation_attempts, 1), 5)
        last_error: Exception | None = None
        for _ in range(attempts):
            if len(prepared) >= count:
                break
            gen_started = time.perf_counter()
            try:
                generated = await generator.generate(
                    project_name=project.name,
                    learning_goal=project.learning_goal,
                    target_outcome=project.target_outcome,
                    concepts=[concept.name],
                    evidence_text=evidence_text,
                    difficulty=difficulty.value,
                    question_type=question_type.value,
                    question_count=count - len(prepared),
                    project_id=project.id,
                )
                from app.services.ai_usage_service import AiUsageService

                AiUsageService(self.session).record(
                    feature="quiz_generate",
                    provider=getattr(generator, "name", "quiz"),
                    model=getattr(generator, "model", "-"),
                    latency_ms=int((time.perf_counter() - gen_started) * 1000),
                    user_id=user_id,
                    project_id=project.id,
                )
            except (AITransientError, QuizGenerationFailed) as e:
                # Bounded retries for both transient failures and malformed
                # structured output; exhaustion is handled after the loop.
                last_error = e
                log_ai_call(
                    provider=getattr(generator, "name", "quiz"),
                    model=getattr(generator, "model", "-"),
                    operation="quiz_generate",
                    latency_ms=0,
                    status="retry",
                    error_type=type(e).__name__,
                    project_id=project.id,
                )
                continue
            for item in generated.questions:
                if len(prepared) >= count:
                    break
                record = self._validate_generated(
                    item,
                    project_concepts=project_concepts,
                    kept_prompts=kept_prompts,
                    provenance_chunks=provenance_chunks,
                    best_similarity=result.best_similarity,
                    model_name=getattr(generator, "model", None),
                )
                if record is not None:
                    prepared.append(record)
                    kept_prompts.add(_normalize_prompt(record.prompt))
            if len(prepared) < count:
                # Malformed batch: one more bounded attempt, then skip.
                continue
        if not prepared and last_error is not None:
            from app.services.ai_usage_service import AiUsageService

            AiUsageService(self.session).record(
                feature="quiz_generate",
                provider=getattr(generator, "name", "quiz"),
                model=getattr(generator, "model", "-"),
                latency_ms=0,
                user_id=user_id,
                project_id=project.id,
                success=False,
                error_type=type(last_error).__name__,
            )
            if isinstance(last_error, AITransientError):
                raise ServiceUnavailableError(
                    "Question generation is temporarily unavailable, please retry."
                ) from last_error
            # Malformed output exhausted its bound: surface the permanent error.
            raise last_error
        return prepared

    def _validate_generated(
        self,
        item,
        *,
        project_concepts: dict[uuid.UUID, Concept],
        kept_prompts: set[str],
        provenance_chunks: list[dict],
        best_similarity: float | None,
        model_name: str | None,
    ) -> PreparedQuestion | None:
        """Deterministic per-question validation. Returns an app-owned record
        or None (with a log line) — malformed output is dropped, never saved,
        and a batch is never partially persisted as valid."""
        from app.ai.schemas import GeneratedQuestion

        if not isinstance(item, GeneratedQuestion):
            try:
                item = GeneratedQuestion.model_validate(
                    item if isinstance(item, dict) else item.__dict__
                )
            except Exception as e:
                log.warning("quiz question failed schema validation err=%s", e)
                return None
        prompt = (item.prompt or "").strip()
        if (
            not prompt
            or len(prompt) < MIN_PROMPT_CHARS
            or len(prompt) > MAX_PROMPT_CHARS
            or _TRIVIAL_RE.match(prompt.lower())
            or _normalize_prompt(prompt) in kept_prompts
        ):
            return None
        try:
            qtype = QuestionType(item.type.strip().upper())
        except ValueError:
            return None
        difficulty = _normalize_difficulty(item.difficulty)
        # Concept names are advisory: resolve against the project, drop the
        # question when nothing resolves (unsupported concept).
        by_name = {_normalize_name(c.name): c for c in project_concepts.values()}
        resolved: list[uuid.UUID] = []
        for raw in list(item.concept_names) + list(item.expected_concepts):
            concept = by_name.get(_normalize_name(str(raw)))
            if concept is not None and concept.id not in resolved:
                resolved.append(concept.id)
        if not resolved:
            log.warning("quiz question dropped: no in-project concept")
            return None
        provenance = {
            "generator": "ai",
            "model": model_name,
            "chunks": provenance_chunks,
            "best_similarity": best_similarity,
            "concept_ids": [str(c) for c in resolved],
        }
        if qtype == QuestionType.MCQ:
            return self._validate_mcq(
                item,
                prompt=prompt,
                resolved=resolved,
                difficulty=difficulty,
                provenance=provenance,
            )
        return self._validate_open(
            item,
            prompt=prompt,
            resolved=resolved,
            difficulty=difficulty,
            provenance=provenance,
            project_concepts=project_concepts,
        )

    def _validate_mcq(
        self,
        item,
        *,
        prompt: str,
        resolved: list[uuid.UUID],
        difficulty: Difficulty,
        provenance: dict,
    ) -> PreparedQuestion | None:
        options: list[dict] = []
        seen_ids: set[str] = set()
        seen_texts: set[str] = set()
        for option in item.options or []:
            oid = str(option.id or "").strip().upper()
            text = str(option.text or "").strip()
            if not oid or not text or not _OPTION_ID_RE.match(oid):
                return None
            if oid in seen_ids or text.lower() in seen_texts:
                return None  # duplicate option ids or texts
            seen_ids.add(oid)
            seen_texts.add(text.lower())
            options.append({"id": oid, "text": text})
        if not (MCQ_MIN_OPTIONS <= len(options) <= MCQ_MAX_OPTIONS):
            return None
        correct = str(item.correct_option_id or "").strip().upper()
        if not correct or correct not in seen_ids:
            return None  # no single valid correct option
        explanation = str(item.explanation or "").strip()
        if not explanation:
            return None
        return PreparedQuestion(
            type=QuestionType.MCQ,
            prompt=prompt,
            options=options,
            correct_option_id=correct,
            explanation=explanation,
            expected_concepts=[],
            reference_answer=None,
            concept_ids=resolved,
            difficulty=difficulty,
            provenance=provenance,
        )

    def _validate_open(
        self,
        item,
        *,
        prompt: str,
        resolved: list[uuid.UUID],
        difficulty: Difficulty,
        provenance: dict,
        project_concepts: dict[uuid.UUID, Concept],
    ) -> PreparedQuestion | None:
        expected = [project_concepts[c].name for c in resolved]
        reference = str(item.reference_answer or "").strip()
        if not expected or not reference:
            return None
        return PreparedQuestion(
            type=QuestionType.OPEN_ENDED,
            prompt=prompt,
            options=None,
            correct_option_id=None,
            explanation=str(item.explanation or "").strip() or None,
            expected_concepts=expected,
            reference_answer=reference,
            concept_ids=resolved,
            difficulty=difficulty,
            provenance=provenance,
        )

    # ------------------------------------------------------------ persistence

    @transactional
    def _persist_quiz(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        prepared: list[PreparedQuestion],
        title: str,
        difficulty: Difficulty | None,
        client_request_key: str | None,
        concept_ids: set[uuid.UUID],
    ) -> Quiz:
        """Single commit: quiz (READY) + questions + concept links (with
        project_id for the composite FKs) + placements + creation event."""
        quiz = self.quizzes.add(
            Quiz(
                project_id=project.id,
                title=title[:200],
                status=QuizStatus.READY,
                difficulty=difficulty,
                generated_by_ai=True,
                generation_metadata={
                    "strategy": "default",
                    "question_count": len(prepared),
                    "concept_ids": [str(c) for c in sorted(concept_ids)],
                },
                client_request_key=client_request_key,
            )
        )
        self.session.flush()
        for position, record in enumerate(prepared):
            question = self.questions.create(
                project_id=project.id,
                type=record.type,
                prompt=record.prompt,
                difficulty=record.difficulty,
                explanation=record.explanation,
                correct_answer=(
                    record.correct_option_id
                    if record.type == QuestionType.MCQ
                    else record.reference_answer
                ),
                options=record.options,
            )
            # Flush for the client-side UUID before links/placements use it.
            self.session.flush()
            question.question_metadata = {
                "provenance": record.provenance,
                "expected_concepts": record.expected_concepts,
            }
            for index, concept_id in enumerate(record.concept_ids):
                self.questions.link_concept(
                    question_id=question.id,
                    concept_id=concept_id,
                    project_id=project.id,
                    is_primary=(index == 0),
                )
            self.quizzes.add_question(
                quiz_id=quiz.id, question_id=question.id, position=position, points=1.0
            )
        self.events.append(
            event_type=EventType.QUIZ_CREATED,
            user_id=user_id,
            project_id=project.id,
            entity_type="quiz",
            entity_id=quiz.id,
            payload={"question_count": len(prepared)},
        )
        return quiz

    @transactional
    def _start_attempt_row(
        self, *, user_id: uuid.UUID, project: Project, quiz: Quiz, total: int
    ) -> QuizAttempt:
        attempt = self.attempts.start(quiz_id=quiz.id, user_id=user_id, project_id=project.id)
        attempt.max_score = float(total)
        attempt.score = 0.0
        self.session.flush()
        self.events.append(
            event_type=EventType.QUIZ_STARTED,
            user_id=user_id,
            project_id=project.id,
            entity_type="quiz_attempt",
            entity_id=attempt.id,
            payload={"quiz_id": str(quiz.id), "question_count": total},
        )
        return attempt

    # ------------------------------------------------------------ learner views

    def quiz_questions_view(self, quiz_id: uuid.UUID) -> list[dict]:
        """Ordered learner-safe question dicts (never correct answers,
        references, or retrieval metadata)."""
        views = []
        for placement in self.quizzes.ordered_questions(quiz_id):
            question = self.session.get(Question, placement.question_id)
            if question is None:
                continue
            views.append(
                self._learner_question(
                    question,
                    position=placement.position,
                    points=placement.points,
                )
            )
        return views

    def _learner_question(self, question: Question, *, position: int, points: float) -> dict:
        links = self.questions.concepts_for_question(question.id)
        return {
            "question_id": question.id,
            "type": question.type,
            "prompt": question.prompt,
            "options": self._learner_options(question),
            "position": position,
            "points": points,
            "difficulty": question.difficulty,
            "concepts": [{"id": link.concept_id, "name": name} for link, name in links],
            "sources": self._provenance_sources(question),
        }

    @staticmethod
    def _learner_options(question: Question) -> list[dict]:
        if question.type != QuestionType.MCQ or not question.options:
            return []
        return [
            {"id": str(o.get("id", "")), "text": str(o.get("text", ""))}
            for o in question.options
            if isinstance(o, dict)
        ]

    @staticmethod
    def _expected_concepts(question: Question) -> list[str]:
        metadata = question.question_metadata or {}
        expected = metadata.get("expected_concepts") or []
        return [str(n) for n in expected if str(n).strip()]

    # ------------------------------------------------------------ answers

    async def submit_answer(
        self,
        *,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        answer: str | None,
    ) -> dict:
        """Validate -> evaluate -> persist -> feedback dict. MCQ evaluation is
        deterministic (no AI); open-ended persists the answer first, evaluates
        after commit, and never loses the learner's text on AI failure."""
        project = self._owned_project(user_id, project_id)
        attempt = self.attempts.get_for_project(attempt_id, project.id, user_id)
        if attempt is None:
            raise NotFoundError("Attempt not found.")
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise ConflictError("This attempt is already completed.")
        question = self.questions.get_for_project(question_id, project.id)
        if question is None:
            raise NotFoundError("Question not found.")
        placement = self.session.scalar(
            sa.select(QuizQuestion).where(
                QuizQuestion.quiz_id == attempt.quiz_id,
                QuizQuestion.question_id == question.id,
            )
        )
        if placement is None:
            raise NotFoundError("Question does not belong to this attempt's quiz.")

        existing = self.attempts.find_answer(attempt.id, question.id)
        if existing is not None and existing.is_correct is not None:
            if self._same_answer(existing.answer, answer, question.type):
                return self._answer_result(attempt, question, placement, existing, replay=True)
            raise ConflictError("This question was already answered.")
        if question.type == QuestionType.MCQ:
            return self._submit_mcq(
                user_id=user_id,
                project=project,
                attempt=attempt,
                question=question,
                placement=placement,
                answer=answer,
                existing_pending=existing,
            )
        return await self._submit_open(
            user_id=user_id,
            project=project,
            attempt=attempt,
            question=question,
            placement=placement,
            answer=answer,
            existing_pending=existing,
        )

    @staticmethod
    def _same_answer(stored: str | None, submitted: str | None, qtype: QuestionType) -> bool:
        if qtype == QuestionType.MCQ:
            return (stored or "").strip().upper() == (submitted or "").strip().upper()
        return (stored or "").strip() == (submitted or "").strip()

    @transactional
    def _submit_mcq(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        attempt: QuizAttempt,
        question: Question,
        placement: QuizQuestion,
        answer: str | None,
        existing_pending: QuestionAttempt | None,
    ) -> dict:
        """Atomic: validate -> deterministic compare -> persist -> event."""
        submitted = (answer or "").strip().upper()
        valid_ids = {o["id"].upper() for o in self._learner_options(question) if o.get("id")}
        if not submitted or submitted not in valid_ids:
            raise BadRequestError("Answer must be one of the question's option ids.")
        correct = submitted == (question.correct_answer or "").strip().upper()
        points = placement.points
        if existing_pending is not None:
            row = existing_pending
            row.answer = submitted
            row.is_correct = correct
            row.score = points if correct else 0.0
            row.feedback = self._mcq_feedback(question, correct)
        else:
            row = self.attempts.answer(
                quiz_attempt_id=attempt.id,
                question_id=question.id,
                answer=submitted,
                is_correct=correct,
                score=points if correct else 0.0,
                feedback=self._mcq_feedback(question, correct),
            )
        self.session.flush()
        self.events.append(
            event_type=EventType.QUESTION_ANSWERED,
            user_id=user_id,
            project_id=project.id,
            entity_type="question_attempt",
            entity_id=row.id,
            payload={
                "quiz_id": str(attempt.quiz_id),
                "attempt_id": str(attempt.id),
                "question_id": str(question.id),
                "is_correct": correct,
                "score": row.score,
            },
        )
        return self._answer_result(attempt, question, placement, row, replay=False)

    def _mcq_feedback(self, question: Question, correct: bool) -> str:
        explanation = (question.explanation or "").strip()
        if correct:
            return f"Correct. {explanation}" if explanation else "Correct."
        if explanation:
            return f"Not quite. {explanation}"
        return "Not quite — review the linked concepts and try the next question."

    async def _submit_open(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        attempt: QuizAttempt,
        question: Question,
        placement: QuizQuestion,
        answer: str | None,
        existing_pending: QuestionAttempt | None,
    ) -> dict:
        """Two-phase: persist the answer first (commit), evaluate after (own
        transaction). AI failure keeps the answer and returns a safe error;
        resubmitting the same answer resumes evaluation without duplicating."""
        settings = self.settings
        text = (answer or "").strip()
        if not text:
            raise BadRequestError("Answer must not be blank.")
        if len(text) > settings.quiz_open_ended_max_answer_chars:
            raise BadRequestError(
                f"Answer exceeds the {settings.quiz_open_ended_max_answer_chars} character limit."
            )
        row = self._persist_open_answer(
            attempt=attempt, question=question, text=text, existing_pending=existing_pending
        )
        evaluation = await self._evaluate_open(
            project=project,
            user_id=user_id,
            attempt=attempt,
            question=question,
            learner_answer=text,
        )
        row = self._persist_open_evaluation(
            user_id=user_id,
            project=project,
            attempt=attempt,
            question=question,
            placement=placement,
            row=row,
            evaluation=evaluation,
        )
        return self._answer_result(attempt, question, placement, row, replay=False)

    @transactional
    def _persist_open_answer(
        self,
        *,
        attempt: QuizAttempt,
        question: Question,
        text: str,
        existing_pending: QuestionAttempt | None,
    ) -> QuestionAttempt:
        if existing_pending is not None:
            existing_pending.answer = text
            return existing_pending
        return self.attempts.answer(
            quiz_attempt_id=attempt.id, question_id=question.id, answer=text
        )

    async def _evaluate_open(
        self,
        *,
        project: Project,
        user_id: uuid.UUID,
        attempt: QuizAttempt,
        question: Question,
        learner_answer: str,
    ):
        """Bounded structured evaluation with app-side normalization. Concept
        lists are filtered against the question's expected concepts so the
        model can never hallucinate mastery inputs; correctness is clamped
        0–1 by the schema and re-clamped here for defense in depth."""
        from app.ai.errors import QuizEvaluationFailed

        settings = self.settings
        evaluator = self._ai().open_ended_evaluator(settings)
        evidence_text = await self._evaluation_evidence(
            project=project, user_id=user_id, question=question
        )
        expected = self._expected_concepts(question)
        attempts = min(max(settings.quiz_max_generation_attempts, 1), 5)
        last_error: Exception | None = None
        for _ in range(attempts):
            eval_started = time.perf_counter()
            try:
                result = await evaluator.evaluate(
                    question_prompt=question.prompt,
                    expected_concepts=expected,
                    reference_answer=question.correct_answer or "",
                    evidence_text=evidence_text,
                    learner_answer=learner_answer,
                    project_id=project.id,
                    quiz_id=attempt.quiz_id,
                    attempt_id=attempt.id,
                    max_tokens=settings.quiz_evaluation_max_tokens,
                )
                from app.services.ai_usage_service import AiUsageService

                AiUsageService(self.session).record(
                    feature="quiz_evaluate",
                    provider=getattr(evaluator, "name", "quiz"),
                    model=getattr(evaluator, "model", "-"),
                    latency_ms=int((time.perf_counter() - eval_started) * 1000),
                    user_id=user_id,
                    project_id=project.id,
                )
            except (AITransientError, QuizEvaluationFailed) as e:
                last_error = e
                continue
            return self._normalize_evaluation(result, expected=expected)
        if isinstance(last_error, AITransientError):
            raise ServiceUnavailableError(
                "Answer evaluation is temporarily unavailable; "
                "your answer is saved and you can retry."
            ) from last_error
        if last_error is not None:
            raise last_error
        raise QuizEvaluationFailed("Answer evaluation failed.")

    @staticmethod
    def _normalize_evaluation(result, *, expected: list[str]) -> dict:
        """Clamp + filter model output into app-owned fields."""
        allowed = {_normalize_name(n) for n in expected if n.strip()}
        understood = [
            n for n in (result.concepts_understood or []) if _normalize_name(n) in allowed
        ]
        missing = [n for n in (result.concepts_missing or []) if _normalize_name(n) in allowed]
        # Missing concepts the model forgot to list are still missing.
        understood_names = {_normalize_name(n) for n in understood}
        for name in expected:
            if _normalize_name(name) not in understood_names and name not in missing:
                missing.append(name)
        correctness = min(max(float(result.correctness), 0.0), 1.0)
        return {
            "correctness": correctness,
            "understanding": result.understanding.value,
            "accuracy": result.accuracy.value,
            "relevance": result.relevance.value,
            "concepts_understood": understood,
            "concepts_missing": missing,
            "feedback": str(result.feedback or "").strip() or "Answer recorded.",
        }

    async def _evaluation_evidence(
        self, *, project: Project, user_id: uuid.UUID, question: Question
    ) -> str:
        """Prefer the question's own stored provenance chunks (exact evidence,
        zero embedding cost); fall back to a bounded fresh retrieval; empty
        string when neither yields anything (the evaluator handles that)."""
        chunk_ids: list[uuid.UUID] = []
        for chunk in (question.question_metadata or {}).get("provenance", {}).get("chunks", []):
            try:
                chunk_ids.append(uuid.UUID(str(chunk.get("chunk_id"))))
            except (ValueError, AttributeError, TypeError):
                continue
        if chunk_ids:
            from app.models.materials import DocumentChunk

            rows = self.session.scalars(
                sa.select(DocumentChunk).where(
                    DocumentChunk.id.in_(chunk_ids),
                    DocumentChunk.project_id == project.id,
                )
            ).all()
            texts = [r.content for r in rows if r.content and r.content.strip()]
            if texts:
                return "\n\n".join(
                    f"[Provenance {i + 1}]\n{t.strip()}" for i, t in enumerate(texts)
                )
        try:
            from app.rag.retrieval import RetrievalService

            settings = self.settings
            retrieval = RetrievalService(
                self.session, self._ai().embedding_service(settings), settings
            )
            result = await retrieval.search(
                user_id=user_id,
                project_id=project.id,
                query=question.prompt[:500],
                top_k=settings.quiz_max_retrieved_chunks,
                max_chunks=settings.quiz_max_retrieved_chunks,
                max_chars=settings.quiz_max_context_chars,
            )
            if not result.insufficient_evidence and result.results:
                return format_chunks_for_prompt(result.results)
        except Exception as e:  # noqa: BLE001 - evidence is best-effort; grade without it
            log.warning("quiz evaluation evidence fallback failed err=%s", e)
        return ""

    @transactional
    def _persist_open_evaluation(
        self,
        *,
        user_id: uuid.UUID,
        project: Project,
        attempt: QuizAttempt,
        question: Question,
        placement: QuizQuestion,
        row: QuestionAttempt,
        evaluation: dict,
    ) -> QuestionAttempt:
        correctness = evaluation["correctness"]
        row.is_correct = correctness >= CORRECT_AT
        row.score = round(correctness * placement.points, 4)
        row.feedback = evaluation["feedback"]
        row.evaluation = evaluation
        self.session.flush()
        self.events.append(
            event_type=EventType.QUESTION_ANSWERED,
            user_id=user_id,
            project_id=project.id,
            entity_type="question_attempt",
            entity_id=row.id,
            payload={
                "quiz_id": str(attempt.quiz_id),
                "attempt_id": str(attempt.id),
                "question_id": str(question.id),
                "is_correct": row.is_correct,
                "score": row.score,
            },
        )
        return row

    def _answer_result(
        self,
        attempt: QuizAttempt,
        question: Question,
        placement: QuizQuestion,
        row: QuestionAttempt,
        *,
        replay: bool,
    ) -> dict:
        """Post-answer payload. For MCQ the correct option and explanation are
        included — the question is already answered, so nothing leaks early."""
        result: dict = {
            "attempt_id": attempt.id,
            "question_id": question.id,
            "is_correct": row.is_correct,
            "score": row.score,
            "points": placement.points,
            "feedback": row.feedback or "",
            "is_retry_replay": replay,
            "evaluation": row.evaluation,
        }
        if question.type == QuestionType.MCQ:
            result["correct_option_id"] = question.correct_answer
        return result

    @staticmethod
    def _provenance_sources(question: Question) -> list[dict]:
        metadata = question.question_metadata or {}
        provenance = metadata.get("provenance") or {}
        return [
            {
                "material_name": str(c.get("material_name", "")),
                "page_start": c.get("page_start"),
                "page_end": c.get("page_end"),
            }
            for c in provenance.get("chunks", [])
            if isinstance(c, dict)
        ]

    # ------------------------------------------------------------ completion

    async def complete_attempt(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> AssessmentResult:
        """Server-side completion: pending open-ended answers are evaluated
        first (bounded), then aggregates + concept performance are computed
        from stored rows (never client totals) and an immutable Assessment is
        persisted. Duplicate completion returns 409; the assessment unique
        constraint on quiz_attempt_id backstops races."""
        project = self._owned_project(user_id, project_id)
        attempt = self.attempts.get_for_project(attempt_id, project.id, user_id)
        if attempt is None:
            raise NotFoundError("Attempt not found.")
        if attempt.status != AttemptStatus.IN_PROGRESS:
            raise ConflictError("This attempt is already completed.")
        if self.assessments.get_by_attempt(attempt.id) is not None:
            raise ConflictError("This attempt already has an assessment.")
        await self._evaluate_pendings(user_id=user_id, project=project, attempt=attempt)
        result = self._finalize_attempt(user_id=user_id, project=project, attempt=attempt)
        # Intelligence follows completion, each in its own transaction:
        # assessment -> mastery -> growth -> recommendations. Any downstream
        # failure is logged, never fails completion, never corrupts records.
        self._apply_mastery(user_id=user_id, project=project, result=result)
        self._refresh_growth(user_id=user_id, project=project, result=result)
        self._refresh_learning_context(user_id=user_id, project=project, result=result)
        self._refresh_recommendations(user_id=user_id, project=project, result=result)
        return result

    def _apply_mastery(
        self, *, user_id: uuid.UUID, project: Project, result: AssessmentResult
    ) -> None:
        """Best-effort synchronous mastery update (fast, deterministic). Any
        failure is logged with the assessment id for safe reprocessing; the
        completed assessment stands regardless."""
        try:
            from app.services.mastery_service import MasteryService

            MasteryService(self.session, settings=self.settings).update_from_assessment(
                user_id=user_id, project_id=project.id, assessment_result=result
            )
        except Exception as e:  # noqa: BLE001 - completion must survive mastery faults
            log.warning(
                "mastery update failed assessment=%s err=%s",
                result.assessment_id,
                e,
            )

    def _refresh_growth(
        self, *, user_id: uuid.UUID, project: Project, result: AssessmentResult
    ) -> None:
        """Best-effort per-concept growth refresh (upserts + aggregate is
        computed live on read)."""
        try:
            from app.services.growth_service import GrowthService

            GrowthService(self.session, settings=self.settings).refresh_after_assessment(
                user_id=user_id,
                project_id=project.id,
                assessment_id=result.assessment_id,
            )
        except Exception as e:  # noqa: BLE001 - completion must survive growth faults
            log.warning(
                "growth refresh failed assessment=%s err=%s",
                result.assessment_id,
                e,
            )

    def _refresh_learning_context(
        self, *, user_id: uuid.UUID, project: Project, result: AssessmentResult
    ) -> None:
        """Best-effort persistent context refresh (deterministic rewrite).
        Runs before recommendations so repeated-mistake patterns are fresh."""
        try:
            from app.services.learning_context_service import LearningContextService

            LearningContextService(self.session).refresh_from_assessment(
                user_id=user_id, project_id=project.id
            )
        except Exception as e:  # noqa: BLE001 - completion must survive context faults
            log.warning(
                "learning context refresh failed assessment=%s err=%s",
                result.assessment_id,
                e,
            )

    def _refresh_recommendations(
        self, *, user_id: uuid.UUID, project: Project, result: AssessmentResult
    ) -> None:
        """Best-effort recommendation refresh (expire resolved, generate
        missing, deduplicated, capped)."""
        try:
            from app.services.recommendation_service import RecommendationService

            RecommendationService(self.session, settings=self.settings).refresh_after_assessment(
                user_id=user_id,
                project_id=project.id,
                assessment_id=result.assessment_id,
            )
        except Exception as e:  # noqa: BLE001 - completion must survive rec faults
            log.warning(
                "recommendation refresh failed assessment=%s err=%s",
                result.assessment_id,
                e,
            )

    async def _evaluate_pendings(
        self, *, user_id: uuid.UUID, project: Project, attempt: QuizAttempt
    ) -> None:
        """Evaluate answers persisted without a score (open-ended rows whose
        AI evaluation failed earlier). Best-effort per row: failures leave the
        row pending and count as incorrect at aggregation."""
        for row in self.attempts.answers_for_attempt(attempt.id):
            if row.score is not None or not (row.answer or "").strip():
                continue
            question = self.session.get(Question, row.question_id)
            if question is None or question.type != QuestionType.OPEN_ENDED:
                continue
            placement = self.session.scalar(
                sa.select(QuizQuestion).where(
                    QuizQuestion.quiz_id == attempt.quiz_id,
                    QuizQuestion.question_id == question.id,
                )
            )
            if placement is None:
                continue
            try:
                evaluation = await self._evaluate_open(
                    project=project,
                    user_id=user_id,
                    attempt=attempt,
                    question=question,
                    learner_answer=row.answer or "",
                )
            except (ServiceUnavailableError, QuizEvaluationFailed) as e:
                log.warning("completion-time evaluation failed attempt=%s err=%s", attempt.id, e)
                continue
            self._persist_open_evaluation(
                user_id=user_id,
                project=project,
                attempt=attempt,
                question=question,
                placement=placement,
                row=row,
                evaluation=evaluation,
            )

    @transactional
    def _finalize_attempt(
        self, *, user_id: uuid.UUID, project: Project, attempt: QuizAttempt
    ) -> AssessmentResult:
        placements = self.quizzes.ordered_questions(attempt.quiz_id)
        answers = {row.question_id: row for row in self.attempts.answers_for_attempt(attempt.id)}
        total_points = sum(p.points for p in placements) or 0.0
        earned = 0.0
        answered = correct = partial = incorrect = 0
        per_question: list[tuple[QuizQuestion, Question | None, QuestionAttempt | None]] = []
        for placement in placements:
            question = self.session.get(Question, placement.question_id)
            row = answers.get(placement.question_id)
            per_question.append((placement, question, row))
            if row is None or not (row.answer or "").strip():
                incorrect += 1  # unanswered counts as incorrect, never silent
                continue
            answered += 1
            earned += row.score or 0.0
            band = self._band(row.score or 0.0, placement.points)
            if band == "correct":
                correct += 1
            elif band == "partial":
                partial += 1
            else:
                incorrect += 1
        score_pct = round(100.0 * earned / total_points, 2) if total_points > 0 else 0.0
        concept_results = self._concept_performance(attempt=attempt, per_question=per_question)
        attempt.status = AttemptStatus.COMPLETED
        attempt.score = round(earned, 4)
        attempt.max_score = total_points
        attempt.completed_at = attempt.completed_at or utcnow()
        assessment = self.assessments.create(
            project_id=project.id, user_id=user_id, quiz_attempt_id=attempt.id
        )
        try:
            self.session.flush()
        except IntegrityError as e:
            self.session.rollback()
            raise ConflictError("This attempt already has an assessment.") from e
        assessment.status = AssessmentStatus.COMPLETED
        assessment.score = score_pct
        assessment.completed_at = attempt.completed_at
        assessment.concept_results = [c.as_dict() for c in concept_results]
        self.session.flush()
        self.events.append(
            event_type=EventType.ASSESSMENT_COMPLETED,
            user_id=user_id,
            project_id=project.id,
            entity_type="assessment",
            entity_id=assessment.id,
            payload={
                "quiz_id": str(attempt.quiz_id),
                "attempt_id": str(attempt.id),
                "score": score_pct,
                "answered": answered,
                "total": len(placements),
                "correct": correct,
                "partial": partial,
            },
        )
        return AssessmentResult(
            assessment_id=assessment.id,
            quiz_attempt_id=attempt.id,
            quiz_id=attempt.quiz_id,
            total_questions=len(placements),
            answered_count=answered,
            correct_count=correct,
            partial_count=partial,
            incorrect_count=incorrect,
            score=score_pct,
            concept_results=concept_results,
        )

    @staticmethod
    def _band(score: float, points: float) -> str:
        normalized = (score / points) if points > 0 else 0.0
        if normalized >= CORRECT_AT:
            return "correct"
        if normalized >= PARTIAL_MIN:
            return "partial"
        return "incorrect"

    def _concept_performance(
        self,
        *,
        attempt: QuizAttempt,
        per_question: list[tuple[QuizQuestion, Question | None, QuestionAttempt | None]],
    ) -> list[ConceptPerformance]:
        """Aggregate rows by concept. Unanswered/pending rows count incorrect.
        ``recent`` carries up to 3 newest outcomes per concept for Prompt 9."""
        by_concept: dict[uuid.UUID, ConceptPerformance] = {}
        order: dict[uuid.UUID, list[tuple[int, str]]] = {}

        def bucket(
            concept_id: uuid.UUID, position: int, outcome: str, earned: float, points: float
        ):
            perf = by_concept.get(concept_id)
            order.setdefault(concept_id, []).append((position, outcome))
            if perf is None:
                return
            perf.questions_seen += 1
            if outcome == "correct":
                perf.correct_count += 1
            elif outcome == "partial":
                perf.partial_count += 1
            else:
                perf.incorrect_count += 1
            perf.normalized_score += earned / points if points > 0 else 0.0

        for position, (placement, question, row) in enumerate(per_question):
            if question is None:
                continue
            links = self.questions.concepts_for_question(question.id)
            if row is None or not (row.answer or "").strip():
                outcome, earned = "incorrect", 0.0
            else:
                outcome = self._band(row.score or 0.0, placement.points)
                earned = row.score or 0.0
            for link, name in links:
                if link.concept_id not in by_concept:
                    by_concept[link.concept_id] = ConceptPerformance(
                        concept_id=link.concept_id, concept_name=name
                    )
                bucket(link.concept_id, position, outcome, earned, placement.points)

        results = []
        for concept_id, perf in by_concept.items():
            if perf.questions_seen:
                perf.normalized_score = round(perf.normalized_score / perf.questions_seen, 4)
            perf.recent = [
                {"correct": "C", "partial": "P", "incorrect": "I"}[o]
                for _, o in sorted(order[concept_id], reverse=True)[:3]
            ]
            results.append(perf)
        results.sort(key=lambda p: p.concept_name.lower())
        return results

    def list_assessments(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> list[dict]:
        """Newest-first assessment summaries with their quiz ids (reload-safe
        result history; full results load on demand)."""
        project = self._owned_project(user_id, project_id)
        summaries = []
        for assessment in self.assessments.list_for_project_user(project.id, user_id):
            quiz_id = None
            if assessment.quiz_attempt_id is not None:
                attempt = self.session.get(QuizAttempt, assessment.quiz_attempt_id)
                quiz_id = attempt.quiz_id if attempt is not None else None
            summaries.append(
                {
                    "id": assessment.id,
                    "quiz_attempt_id": assessment.quiz_attempt_id,
                    "quiz_id": quiz_id,
                    "status": assessment.status,
                    "score": assessment.score,
                    "completed_at": assessment.completed_at,
                }
            )
        return summaries

    def get_assessment(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID, assessment_id: uuid.UUID
    ) -> AssessmentResult:
        """Rebuild the result contract from the immutable record. Counts are
        recomputed from attempt rows; per-concept numbers come from the stored
        snapshot (falling back to live computation for legacy NULLs)."""
        project = self._owned_project(user_id, project_id)
        assessment = self.assessments.get_for_project(assessment_id, project.id)
        if assessment is None or assessment.user_id != user_id:
            raise NotFoundError("Assessment not found.")
        if assessment.quiz_attempt_id is None:
            raise NotFoundError("Assessment has no attempt.")
        attempt = self.attempts.get_for_project(assessment.quiz_attempt_id, project.id, user_id)
        if attempt is None:
            raise NotFoundError("Attempt not found.")
        placements = self.quizzes.ordered_questions(attempt.quiz_id)
        answers = {row.question_id: row for row in self.attempts.answers_for_attempt(attempt.id)}
        answered_count = correct = partial = incorrect = 0
        for placement in placements:
            row = answers.get(placement.question_id)
            if row is None or not (row.answer or "").strip():
                incorrect += 1
                continue
            answered_count += 1
            band = self._band(row.score or 0.0, placement.points)
            if band == "correct":
                correct += 1
            elif band == "partial":
                partial += 1
            else:
                incorrect += 1
        concept_results = self._stored_or_live_concepts(assessment, attempt, placements, answers)
        return AssessmentResult(
            assessment_id=assessment.id,
            quiz_attempt_id=attempt.id,
            quiz_id=attempt.quiz_id,
            total_questions=len(placements),
            answered_count=answered_count,
            correct_count=correct,
            partial_count=partial,
            incorrect_count=incorrect,
            score=assessment.score if assessment.score is not None else 0.0,
            concept_results=concept_results,
        )

    def _stored_or_live_concepts(
        self,
        assessment: Assessment,
        attempt: QuizAttempt,
        placements: list[QuizQuestion],
        answers: dict[uuid.UUID, QuestionAttempt],
    ) -> list[ConceptPerformance]:
        stored = assessment.concept_results or []
        results: list[ConceptPerformance] = []
        for entry in stored:
            try:
                results.append(
                    ConceptPerformance(
                        concept_id=uuid.UUID(str(entry["concept_id"])),
                        concept_name=str(entry.get("concept_name", "")),
                        questions_seen=int(entry.get("questions_seen", 0)),
                        correct_count=int(entry.get("correct_count", 0)),
                        partial_count=int(entry.get("partial_count", 0)),
                        incorrect_count=int(entry.get("incorrect_count", 0)),
                        normalized_score=float(entry.get("normalized_score", 0.0)),
                        recent=[str(r) for r in (entry.get("recent") or [])][:3],
                    )
                )
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
        if results or not placements:
            return sorted(results, key=lambda p: p.concept_name.lower())
        per_question = [
            (p, self.session.get(Question, p.question_id), answers.get(p.question_id))
            for p in placements
        ]
        return self._concept_performance(attempt=attempt, per_question=per_question)
