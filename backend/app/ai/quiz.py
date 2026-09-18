"""Quiz AI boundary: grounded question generation and open-ended evaluation.

Both classes use the shared chat provider (Groq in production, deterministic
fake when ``TEST_FAKE_AI`` is set) with Pydantic-validated structured output.
They never touch the database, never decide authorization, and never mint
scores — the application validates, clamps, and persists everything.
"""

from __future__ import annotations

import logging
import time

from app.ai.observability import log_ai_call
from app.ai.prompts import build_quiz_evaluation_prompt, build_quiz_generation_prompt

log = logging.getLogger("app.ai")


class QuestionGenerator:
    """Concept-grounded question generation via structured chat JSON."""

    def __init__(self, chat_provider, *, model: str) -> None:
        self.chat_provider = chat_provider
        self.model = model
        self.name = getattr(chat_provider, "name", "groq-quiz")

    async def generate(
        self,
        *,
        project_name: str,
        learning_goal: str | None,
        target_outcome: str | None,
        concepts: list[str],
        evidence_text: str,
        difficulty: str,
        question_type: str,
        question_count: int,
        project_id=None,
        max_tokens: int | None = None,
    ):
        """Return a validated ``GeneratedQuestionSet``. Malformed output
        raises ``QuizGenerationFailed`` (the caller bounds retries)."""
        from app.ai.errors import QuizGenerationFailed
        from app.ai.schemas import GeneratedQuestionSet

        if not evidence_text or not evidence_text.strip():
            raise QuizGenerationFailed("Cannot generate questions without evidence.")
        system, user = build_quiz_generation_prompt(
            project_name=project_name,
            learning_goal=learning_goal,
            target_outcome=target_outcome,
            concepts=concepts,
            evidence_text=evidence_text,
            difficulty=difficulty,
            question_type=question_type,
            question_count=question_count,
        )
        started = time.perf_counter()
        try:
            raw = await self.chat_provider.chat_json(
                system=system, user=user, model=self.model, max_tokens=max_tokens
            )
        except Exception as e:
            from app.ai.errors import AITransientError

            if isinstance(e, AITransientError):
                raise
            raise QuizGenerationFailed(f"Question generation failed: {type(e).__name__}.") from e
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            result = GeneratedQuestionSet.model_validate(raw)
        except Exception as e:
            log.warning("quiz generation output failed validation err=%s", e)
            raise QuizGenerationFailed("Question generation returned malformed output.") from e
        log_ai_call(
            provider=self.name,
            model=self.model,
            operation="quiz_generate",
            latency_ms=latency_ms,
            status="ok",
            project_id=project_id,
            question_count=len(result.questions),
            concept_count=len(concepts),
        )
        return result


class OpenEndedEvaluator:
    """Structured evaluation of open-ended learner answers."""

    def __init__(self, chat_provider, *, model: str) -> None:
        self.chat_provider = chat_provider
        self.model = model
        self.name = getattr(chat_provider, "name", "groq-quiz-eval")

    async def evaluate(
        self,
        *,
        question_prompt: str,
        expected_concepts: list[str],
        reference_answer: str,
        evidence_text: str,
        learner_answer: str,
        project_id=None,
        quiz_id=None,
        attempt_id=None,
        max_tokens: int | None = None,
    ):
        """Return a validated ``OpenEndedEvaluation``. Invalid output raises
        ``QuizEvaluationFailed`` (the caller bounds retries and never marks
        the answer correct on failure)."""
        from app.ai.errors import QuizEvaluationFailed
        from app.ai.schemas import OpenEndedEvaluation

        system, user = build_quiz_evaluation_prompt(
            question_prompt=question_prompt,
            expected_concepts=expected_concepts,
            reference_answer=reference_answer,
            evidence_text=evidence_text,
            learner_answer=learner_answer,
        )
        started = time.perf_counter()
        try:
            raw = await self.chat_provider.chat_json(
                system=system, user=user, model=self.model, max_tokens=max_tokens
            )
        except Exception as e:
            from app.ai.errors import AITransientError

            if isinstance(e, AITransientError):
                raise
            raise QuizEvaluationFailed(f"Answer evaluation failed: {type(e).__name__}.") from e
        latency_ms = int((time.perf_counter() - started) * 1000)
        try:
            result = OpenEndedEvaluation.model_validate(raw)
        except Exception as e:
            log.warning("quiz evaluation output failed validation err=%s", e)
            raise QuizEvaluationFailed("Answer evaluation returned malformed output.") from e
        log_ai_call(
            provider=self.name,
            model=self.model,
            operation="quiz_evaluate",
            latency_ms=latency_ms,
            status="ok",
            project_id=project_id,
            quiz_id=quiz_id,
            attempt_id=attempt_id,
            question_type="OPEN_ENDED",
        )
        return result
