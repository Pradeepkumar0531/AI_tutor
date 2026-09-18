"""Assessment chain repositories: quizzes, questions, joins, attempts, assessments."""

from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.models.assessment import (
    Assessment,
    Question,
    QuestionAttempt,
    QuestionConcept,
    Quiz,
    QuizAttempt,
    QuizQuestion,
)
from app.models.enums import (
    AssessmentStatus,
    AttemptStatus,
    Difficulty,
    QuestionType,
)
from app.models.mixins import utcnow
from app.repositories.base import BaseRepository


class QuizRepository(BaseRepository[Quiz]):
    model = Quiz

    def create(self, *, project_id: uuid.UUID, title: str, description: str | None = None) -> Quiz:
        return self.add(Quiz(project_id=project_id, title=title.strip(), description=description))

    def get_many_for_project(self, quiz_ids: list[uuid.UUID], project_id: uuid.UUID) -> list[Quiz]:
        """Batch-resolve quizzes known to belong to a project (timeline names)."""
        if not quiz_ids:
            return []
        return list(
            self.session.scalars(
                sa.select(Quiz).where(Quiz.id.in_(quiz_ids), Quiz.project_id == project_id)
            )
        )

    def get_for_project(self, quiz_id: uuid.UUID, project_id: uuid.UUID) -> Quiz | None:
        return self.session.scalar(
            sa.select(Quiz).where(Quiz.id == quiz_id, Quiz.project_id == project_id)
        )

    def list_for_project(self, project_id: uuid.UUID) -> list[Quiz]:
        """Newest-first quizzes for one owned project."""
        return list(
            self.session.scalars(
                sa.select(Quiz)
                .where(Quiz.project_id == project_id)
                .order_by(Quiz.created_at.desc(), Quiz.id.desc())
            )
        )

    def find_by_client_key(self, project_id: uuid.UUID, client_key: str) -> Quiz | None:
        """Idempotent creation: the same client key resolves to the original quiz."""
        return self.session.scalar(
            sa.select(Quiz).where(
                Quiz.project_id == project_id, Quiz.client_request_key == client_key
            )
        )

    def add_question(
        self,
        *,
        quiz_id: uuid.UUID,
        question_id: uuid.UUID,
        position: int,
        points: float = 1.0,
    ) -> QuizQuestion:
        """Strict placement: re-adding the same question raises IntegrityError;
        reposition via update, not silent upsert."""
        return self.add(
            QuizQuestion(quiz_id=quiz_id, question_id=question_id, position=position, points=points)
        )

    def question_counts(self, project_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Single-query question totals per quiz for list views."""
        rows = self.session.execute(
            sa.select(QuizQuestion.quiz_id, sa.func.count())
            .join(Quiz, Quiz.id == QuizQuestion.quiz_id)
            .where(Quiz.project_id == project_id)
            .group_by(QuizQuestion.quiz_id)
        )
        return {quiz_id: total for quiz_id, total in rows}

    def ordered_questions(self, quiz_id: uuid.UUID) -> list[QuizQuestion]:
        return list(
            self.session.scalars(
                sa.select(QuizQuestion)
                .where(QuizQuestion.quiz_id == quiz_id)
                .order_by(QuizQuestion.position)
            )
        )


class QuestionRepository(BaseRepository[Question]):
    model = Question

    def create(
        self,
        *,
        project_id: uuid.UUID,
        type: QuestionType,
        prompt: str,
        difficulty: Difficulty | None = None,
        explanation: str | None = None,
        correct_answer: str | None = None,
        options: list | None = None,
    ) -> Question:
        return self.add(
            Question(
                project_id=project_id,
                type=type,
                prompt=prompt,
                difficulty=difficulty,
                explanation=explanation,
                correct_answer=correct_answer,
                options=options,
            )
        )

    def get_for_project(self, question_id: uuid.UUID, project_id: uuid.UUID) -> Question | None:
        return self.session.scalar(
            sa.select(Question).where(Question.id == question_id, Question.project_id == project_id)
        )

    def link_concept(
        self,
        *,
        question_id: uuid.UUID,
        concept_id: uuid.UUID,
        project_id: uuid.UUID,
        weight: float = 1.0,
        is_primary: bool = False,
    ) -> QuestionConcept:
        """Same-project pairing is verified by the caller (service layer); the
        composite database FKs reject cross-project links regardless."""
        return self.add(
            QuestionConcept(
                question_id=question_id,
                concept_id=concept_id,
                project_id=project_id,
                weight=weight,
                is_primary=is_primary,
            )
        )

    def candidates_for_concept(
        self,
        concept_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        exclude_ids: set[uuid.UUID],
        limit: int = 10,
    ) -> list[Question]:
        """Existing project questions linked to a concept, excluding recently
        served ones. Oldest first (stable rotation); the caller caps ``limit``."""
        stmt = (
            sa.select(Question)
            .join(QuestionConcept, QuestionConcept.question_id == Question.id)
            .where(
                QuestionConcept.concept_id == concept_id,
                Question.project_id == project_id,
            )
            .order_by(Question.created_at, Question.id)
            .limit(min(max(limit, 1), 50))
        )
        if exclude_ids:
            stmt = stmt.where(Question.id.notin_(exclude_ids))
        return list(self.session.scalars(stmt))

    def concepts_for_question(self, question_id: uuid.UUID) -> list[tuple[QuestionConcept, str]]:
        """(link, concept name) pairs for one question, primary first."""
        from app.models.knowledge import Concept

        return [
            (link, name)
            for link, name in self.session.execute(
                sa.select(QuestionConcept, Concept.name)
                .join(Concept, Concept.id == QuestionConcept.concept_id)
                .where(QuestionConcept.question_id == question_id)
                .order_by(QuestionConcept.is_primary.desc(), Concept.name)
            ).all()
        ]

    def recent_prompts(self, project_id: uuid.UUID, *, limit: int = 50) -> list[str]:
        """Bounded exposure window: prompts of recently generated project
        questions, newest first. Drives duplicate avoidance."""
        limit = min(max(limit, 1), 200)
        return list(
            self.session.scalars(
                sa.select(Question.prompt)
                .where(Question.project_id == project_id)
                .order_by(Question.created_at.desc(), Question.id.desc())
                .limit(limit)
            )
        )


class AttemptRepository(BaseRepository[QuizAttempt]):
    model = QuizAttempt

    def start(
        self, *, quiz_id: uuid.UUID, user_id: uuid.UUID, project_id: uuid.UUID
    ) -> QuizAttempt:
        return self.add(QuizAttempt(quiz_id=quiz_id, user_id=user_id, project_id=project_id))

    def count_for_project_user(self, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(QuizAttempt.id)).where(
                    QuizAttempt.project_id == project_id,
                    QuizAttempt.user_id == user_id,
                )
            )
            or 0
        )

    def get_for_project(
        self, attempt_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> QuizAttempt | None:
        return self.session.scalar(
            sa.select(QuizAttempt).where(
                QuizAttempt.id == attempt_id,
                QuizAttempt.project_id == project_id,
                QuizAttempt.user_id == user_id,
            )
        )

    def answer(
        self,
        *,
        quiz_attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        answer: str | None,
        is_correct: bool | None = None,
        score: float | None = None,
        feedback: str | None = None,
        evaluation: dict | None = None,
    ) -> QuestionAttempt:
        return self.add(
            QuestionAttempt(
                quiz_attempt_id=quiz_attempt_id,
                question_id=question_id,
                answer=answer,
                is_correct=is_correct,
                score=score,
                feedback=feedback,
                evaluation=evaluation,
            )
        )

    def find_active(self, quiz_id: uuid.UUID, user_id: uuid.UUID) -> QuizAttempt | None:
        """Newest IN_PROGRESS attempt: reload/StrictMode resume without
        duplicating attempts."""
        return self.session.scalar(
            sa.select(QuizAttempt)
            .where(
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.user_id == user_id,
                QuizAttempt.status == AttemptStatus.IN_PROGRESS,
            )
            .order_by(QuizAttempt.started_at.desc(), QuizAttempt.id.desc())
        )

    def answers_for_attempt(self, quiz_attempt_id: uuid.UUID) -> list[QuestionAttempt]:
        return list(
            self.session.scalars(
                sa.select(QuestionAttempt)
                .where(QuestionAttempt.quiz_attempt_id == quiz_attempt_id)
                .order_by(QuestionAttempt.answered_at, QuestionAttempt.id)
            )
        )

    def find_answer(
        self, quiz_attempt_id: uuid.UUID, question_id: uuid.UUID
    ) -> QuestionAttempt | None:
        return self.session.scalar(
            sa.select(QuestionAttempt).where(
                QuestionAttempt.quiz_attempt_id == quiz_attempt_id,
                QuestionAttempt.question_id == question_id,
            )
        )

    def recent_concept_outcomes(
        self, project_id: uuid.UUID, user_id: uuid.UUID, *, limit: int = 50
    ) -> list[tuple[uuid.UUID, bool | None, float | None]]:
        """Bounded (concept_id, is_correct, score) history, newest first —
        feeds the selection strategy. Pending evaluations (NULL) are included
        so the strategy can see exposure even before scoring."""
        from app.models.assessment import QuestionAttempt as QuestionAttemptModel

        limit = min(max(limit, 1), 200)
        return [
            (concept_id, is_correct, score)
            for concept_id, is_correct, score in self.session.execute(
                sa.select(
                    QuestionConcept.concept_id,
                    QuestionAttemptModel.is_correct,
                    QuestionAttemptModel.score,
                )
                .join(
                    QuestionAttemptModel,
                    QuestionAttemptModel.question_id == QuestionConcept.question_id,
                )
                .join(
                    QuizAttempt,
                    QuizAttempt.id == QuestionAttemptModel.quiz_attempt_id,
                )
                .where(
                    QuizAttempt.project_id == project_id,
                    QuizAttempt.user_id == user_id,
                )
                .order_by(QuestionAttemptModel.answered_at.desc(), QuestionAttemptModel.id.desc())
                .limit(limit)
            ).all()
        ]


class AssessmentRepository(BaseRepository[Assessment]):
    model = Assessment

    def create(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        quiz_attempt_id: uuid.UUID | None = None,
    ) -> Assessment:
        return self.add(
            Assessment(project_id=project_id, user_id=user_id, quiz_attempt_id=quiz_attempt_id)
        )

    def get_for_project(self, assessment_id: uuid.UUID, project_id: uuid.UUID) -> Assessment | None:
        return self.session.scalar(
            sa.select(Assessment).where(
                Assessment.id == assessment_id, Assessment.project_id == project_id
            )
        )

    def get_by_attempt(self, quiz_attempt_id: uuid.UUID) -> Assessment | None:
        return self.session.scalar(
            sa.select(Assessment).where(Assessment.quiz_attempt_id == quiz_attempt_id)
        )

    def list_for_project_user(self, project_id: uuid.UUID, user_id: uuid.UUID) -> list[Assessment]:
        return list(
            self.session.scalars(
                sa.select(Assessment)
                .where(Assessment.project_id == project_id, Assessment.user_id == user_id)
                .order_by(Assessment.created_at.desc(), Assessment.id.desc())
            )
        )

    def count_for_project_user(self, project_id: uuid.UUID, user_id: uuid.UUID) -> int:
        return (
            self.session.scalar(
                sa.select(sa.func.count(Assessment.id)).where(
                    Assessment.project_id == project_id, Assessment.user_id == user_id
                )
            )
            or 0
        )

    def recent_for_project_user(
        self, project_id: uuid.UUID, user_id: uuid.UUID, *, limit: int = 100
    ) -> list[Assessment]:
        """Newest-first bounded window for growth history/aggregation."""
        return list(
            self.session.scalars(
                sa.select(Assessment)
                .where(Assessment.project_id == project_id, Assessment.user_id == user_id)
                .order_by(Assessment.completed_at.desc(), Assessment.id.desc())
                .limit(min(max(limit, 1), 200))
            )
        )

    def complete(self, assessment: Assessment, *, score: float) -> Assessment:
        assessment.status = AssessmentStatus.COMPLETED
        assessment.score = score
        assessment.completed_at = utcnow()
        return assessment
