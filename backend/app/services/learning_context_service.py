"""Persistent relevant learning context: derived state, not conversation logs.

One ``LearningContext`` row per (user, project), rewritten (never appended)
on every refresh so reprocessing is idempotent. Signals are deterministic:
mastery scores, trends, and counted misses from real question history — no LLM
needed, no fabricated memory. Tutor prompts receive only a bounded slice via
``context_for_tutor``.
"""

from __future__ import annotations

import logging
import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.models.assessment import QuestionAttempt, QuestionConcept, QuizAttempt
from app.models.context import LearningContext
from app.models.enums import MasteryTrend
from app.models.intelligence import Mastery
from app.models.knowledge import Concept
from app.models.learning import Project
from app.services.base import BaseService, transactional

log = logging.getLogger("app.learning_context")

#: A concept becomes a "repeated mistake" pattern at this many misses.
REPEATED_MISS_THRESHOLD = 2
#: Only recent attempts feed pattern detection (bounded, relevant).
RECENT_ATTEMPTS_WINDOW = 20
#: Mastery bands for strengths / weaknesses.
STRENGTH_SCORE = 80.0
WEAKNESS_SCORE = 50.0
#: Hard budget for the tutor-injected context block.
MAX_CONTEXT_CHARS = 1200


class LearningContextService(BaseService):
    def __init__(self, session: Session) -> None:
        super().__init__(session)

    def get_or_create(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> LearningContext:
        ctx = self.session.scalars(
            sa.select(LearningContext).where(
                LearningContext.user_id == user_id,
                LearningContext.project_id == project_id,
            )
        ).one_or_none()
        if ctx is None:
            ctx = LearningContext(user_id=user_id, project_id=project_id)
            self.session.add(ctx)
            self.session.flush()
        return ctx

    def get(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> LearningContext | None:
        return self.session.scalars(
            sa.select(LearningContext).where(
                LearningContext.user_id == user_id,
                LearningContext.project_id == project_id,
            )
        ).one_or_none()

    @transactional
    def refresh_from_assessment(
        self, *, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> LearningContext:
        """Rewrite derived context from current mastery + recent history.

        Idempotent: output depends only on current rows, so duplicate runs
        converge to the same state (no duplicate patterns, no growth).
        """
        ctx = self.get_or_create(user_id=user_id, project_id=project_id)
        project = self.session.get(Project, project_id)

        mastery_rows = self.session.scalars(
            sa.select(Mastery)
            .where(Mastery.user_id == user_id, Mastery.project_id == project_id)
            .order_by(Mastery.score.asc())
        ).all()
        names = self._concept_names(project_id)
        ctx.strengths = [
            {
                "concept_id": str(m.concept_id),
                "concept_name": names.get(m.concept_id, "?"),
                "score": round(m.score, 1),
            }
            for m in mastery_rows
            if m.score >= STRENGTH_SCORE
        ][:5]
        ctx.weaknesses = [
            {
                "concept_id": str(m.concept_id),
                "concept_name": names.get(m.concept_id, "?"),
                "score": round(m.score, 1),
                "trend": str(m.trend),
            }
            for m in mastery_rows
            if m.score < WEAKNESS_SCORE
        ][:5]

        misses = self._recent_misses(user_id=user_id, project_id=project_id)
        ctx.repeated_mistakes = [
            {
                "concept_id": str(cid),
                "concept_name": names.get(cid, "?"),
                "misses": n,
                "window_attempts": RECENT_ATTEMPTS_WINDOW,
            }
            for cid, n in misses.items()
            if n >= REPEATED_MISS_THRESHOLD
        ]

        notes: list[str] = []
        declining = [
            names.get(m.concept_id, "?") for m in mastery_rows if m.trend == MasteryTrend.DECLINING
        ][:3]
        if declining:
            notes.append(f"Declining mastery: {', '.join(declining)}.")
        if ctx.repeated_mistakes:
            pat = ", ".join(
                f"{p['concept_name']} ({p['misses']} misses)" for p in ctx.repeated_mistakes[:3]
            )
            notes.append(f"Repeated mistakes: {pat}.")
        ctx.notes = notes
        ctx.learning_goal = project.learning_goal if project else None
        self.session.flush()
        log.info(
            "context refreshed user=%s project=%s weak=%d repeat=%d",
            user_id,
            project_id,
            len(ctx.weaknesses),
            len(ctx.repeated_mistakes),
        )
        return ctx

    def context_for_tutor(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> str:
        """Bounded plain-text block for tutor prompts. Empty when nothing
        useful is known — never padding, never full history."""
        ctx = self.get(user_id=user_id, project_id=project_id)
        if ctx is None:
            return ""
        parts: list[str] = []
        if ctx.learning_goal:
            parts.append(f"Learning goal: {ctx.learning_goal}")
        if ctx.weaknesses:
            weak = ", ".join(f"{w['concept_name']} ({w['score']}%)" for w in ctx.weaknesses[:3])
            parts.append(f"Known weaknesses: {weak}")
        if ctx.repeated_mistakes:
            rep = ", ".join(
                f"{r['concept_name']} ({r['misses']} misses)" for r in ctx.repeated_mistakes[:3]
            )
            parts.append(f"Repeated mistakes: {rep}")
        if ctx.strengths:
            strong = ", ".join(s["concept_name"] for s in ctx.strengths[:3])
            parts.append(f"Known strengths: {strong}")
        out = "\n".join(parts)
        return out[:MAX_CONTEXT_CHARS]

    def repeated_concept_ids(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> list[uuid.UUID]:
        ctx = self.get(user_id=user_id, project_id=project_id)
        if ctx is None:
            return []
        return [uuid.UUID(p["concept_id"]) for p in ctx.repeated_mistakes]

    def _concept_names(self, project_id: uuid.UUID) -> dict[uuid.UUID, str]:
        rows = self.session.execute(
            sa.select(Concept.id, Concept.name).where(Concept.project_id == project_id)
        ).all()
        return {r[0]: r[1] for r in rows}

    def _recent_misses(self, *, user_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Count incorrect answers per concept over the recent attempt window."""
        recent_attempt_ids = self.session.scalars(
            sa.select(QuizAttempt.id)
            .where(QuizAttempt.user_id == user_id, QuizAttempt.project_id == project_id)
            .order_by(QuizAttempt.started_at.desc())
            .limit(RECENT_ATTEMPTS_WINDOW)
        ).all()
        if not recent_attempt_ids:
            return {}
        rows = self.session.execute(
            sa.select(QuestionConcept.concept_id, sa.func.count())
            .join(
                QuestionAttempt,
                QuestionAttempt.question_id == QuestionConcept.question_id,
            )
            .where(
                QuestionAttempt.quiz_attempt_id.in_(recent_attempt_ids),
                QuestionAttempt.is_correct.is_(False),
            )
            .group_by(QuestionConcept.concept_id)
        ).all()
        return {r[0]: r[1] for r in rows}
