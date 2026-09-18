"""Persistent learning context: derivation, idempotency, bounded retrieval."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.assessment import Question, QuestionAttempt, QuestionConcept, QuizAttempt
from app.models.enums import AttemptStatus, MasteryTrend, QuestionType
from app.models.intelligence import Mastery
from app.services.learning_context_service import LearningContextService
from tests.conftest import make_project, make_user


def _seed_mastery(session: Session, user, project, concept_name: str, score: float):
    from app.models.knowledge import Concept

    concept = Concept(
        project_id=project.id, name=concept_name, normalized_name=concept_name.lower()
    )
    session.add(concept)
    session.flush()
    session.add(
        Mastery(
            user_id=user.id,
            project_id=project.id,
            concept_id=concept.id,
            score=score,
            confidence=0.9,
            trend=MasteryTrend.STABLE,
        )
    )
    session.commit()
    return concept


def _miss(session: Session, user, project, concept, n: int = 2):
    from app.models.assessment import Quiz

    q = Question(
        project_id=project.id,
        type=QuestionType.MCQ,
        prompt="Probe?",
        options=[{"id": "A", "text": "y"}, {"id": "B", "text": "n"}],
        correct_answer="A",
    )
    session.add(q)
    session.flush()
    session.add(
        QuestionConcept(question_id=q.id, concept_id=concept.id, project_id=project.id, weight=1.0)
    )
    quiz = Quiz(project_id=project.id, title="Probe quiz")
    session.add(quiz)
    session.flush()
    for _ in range(n):
        att = QuizAttempt(
            quiz_id=quiz.id,
            user_id=user.id,
            project_id=project.id,
            status=AttemptStatus.COMPLETED,
        )
        session.add(att)
        session.flush()
        session.add(
            QuestionAttempt(
                quiz_attempt_id=att.id,
                question_id=q.id,
                answer="B",
                is_correct=False,
                score=0.0,
            )
        )
    session.commit()


def test_refresh_derives_weakness_strength_pattern(session: Session) -> None:
    user = make_user(session)
    project = make_project(session, user)
    weak = _seed_mastery(session, user, project, "Weakness", 20.0)
    _seed_mastery(session, user, project, "Strength", 90.0)
    _miss(session, user, project, weak, n=2)

    svc = LearningContextService(session)
    ctx = svc.refresh_from_assessment(user_id=user.id, project_id=project.id)
    assert any(w["concept_name"] == "Weakness" for w in ctx.weaknesses)
    assert any(s["concept_name"] == "Strength" for s in ctx.strengths)
    assert any(p["concept_name"] == "Weakness" and p["misses"] >= 2 for p in ctx.repeated_mistakes)


def test_single_miss_is_not_a_pattern(session: Session) -> None:
    user = make_user(session)
    project = make_project(session, user)
    weak = _seed_mastery(session, user, project, "Weakness", 20.0)
    _miss(session, user, project, weak, n=1)

    ctx = LearningContextService(session).refresh_from_assessment(
        user_id=user.id, project_id=project.id
    )
    assert ctx.repeated_mistakes == []


def test_refresh_is_idempotent(session: Session) -> None:
    user = make_user(session)
    project = make_project(session, user)
    weak = _seed_mastery(session, user, project, "Weakness", 20.0)
    _miss(session, user, project, weak, n=3)

    svc = LearningContextService(session)
    first = svc.refresh_from_assessment(user_id=user.id, project_id=project.id)
    second = svc.refresh_from_assessment(user_id=user.id, project_id=project.id)
    assert first.id == second.id
    assert first.repeated_mistakes == second.repeated_mistakes
    assert len(second.repeated_mistakes) == 1


def test_context_for_tutor_bounded_and_scoped(session: Session) -> None:
    user = make_user(session)
    project = make_project(session, user)
    other = make_project(session, user, name="Other")

    svc = LearningContextService(session)
    assert svc.context_for_tutor(user_id=user.id, project_id=other.id) == ""
    weak = _seed_mastery(session, user, project, "Weakness", 20.0)
    _miss(session, user, project, weak, n=2)
    svc.refresh_from_assessment(user_id=user.id, project_id=project.id)
    text = svc.context_for_tutor(user_id=user.id, project_id=project.id)
    assert "Weakness" in text and len(text) <= 1200
    # Other project's context is independent.
    assert svc.context_for_tutor(user_id=user.id, project_id=other.id) == ""


def test_repeated_mistake_generates_targeted_recommendation(session: Session) -> None:
    import sqlalchemy as sa

    from app.models.enums import RecommendationStatus
    from app.models.intelligence import Recommendation
    from app.services.recommendation_service import RecommendationService

    user = make_user(session)
    project = make_project(session, user)
    weak = _seed_mastery(session, user, project, "Weakness", 20.0)
    _miss(session, user, project, weak, n=2)
    LearningContextService(session).refresh_from_assessment(user_id=user.id, project_id=project.id)
    RecommendationService(session).refresh_after_assessment(user_id=user.id, project_id=project.id)
    targeted = session.scalars(
        sa.select(Recommendation).where(
            Recommendation.user_id == user.id,
            Recommendation.project_id == project.id,
            Recommendation.status == RecommendationStatus.ACTIVE,
            Recommendation.concept_id == weak.id,
        )
    ).all()
    assert any("Repeated mistakes" in (r.reason or "") for r in targeted)
    # Second refresh creates no duplicate.
    RecommendationService(session).refresh_after_assessment(user_id=user.id, project_id=project.id)
    again = session.scalars(
        sa.select(Recommendation).where(
            Recommendation.user_id == user.id,
            Recommendation.project_id == project.id,
            Recommendation.status == RecommendationStatus.ACTIVE,
            Recommendation.concept_id == weak.id,
        )
    ).all()
    assert len(again) == len(targeted)
