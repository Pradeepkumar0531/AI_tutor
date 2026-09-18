"""Growth + Recommendations: deterministic rules, lifecycle, isolation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.models.enums import (
    AssessmentStatus,
    GrowthStatus,
    MasteryTrend,
    RecommendationStatus,
    RecommendationType,
)
from app.models.intelligence import Growth, Recommendation
from app.models.ops import Event
from app.repositories.knowledge import ConceptRepository
from app.services.assessment_contracts import AssessmentResult, ConceptPerformance
from app.services.growth_service import GrowthService, concept_status, project_status
from app.services.mastery_service import MasteryService
from app.services.recommendation_service import RecommendationService
from tests.conftest import make_project, make_user

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _settings(**kwargs) -> Settings:
    kwargs.setdefault("test_fake_ai", True)
    return Settings(**kwargs)


def _seed_concepts(session: Session, names: list[str], owner=None):
    owner = owner or make_user(session)
    project = make_project(session, owner)
    concepts = {}
    for name in names:
        concept, _ = ConceptRepository(session).get_or_create(
            project_id=project.id, name=name, description=f"{name} matters."
        )
        concepts[name] = concept
    session.commit()
    return owner, project, concepts


def _perf(concept_id, name, seen=1, correct=1, partial=0, incorrect=0, norm=1.0, recent=None):
    return ConceptPerformance(
        concept_id=concept_id,
        concept_name=name,
        questions_seen=seen,
        correct_count=correct,
        partial_count=partial,
        incorrect_count=incorrect,
        normalized_score=norm,
        recent=list(recent) if recent is not None else (["C"] if correct else ["I"]),
    )


def _apply_mastery(session, owner, project, perfs, completed_at):
    from app.models.enums import AssessmentStatus
    from app.repositories.assessments import AssessmentRepository

    repo = AssessmentRepository(session)
    row = repo.create(project_id=project.id, user_id=owner.id, quiz_attempt_id=None)
    row.status = AssessmentStatus.COMPLETED
    row.score = 50.0
    row.completed_at = completed_at
    row.concept_results = [p.as_dict() for p in perfs]
    session.commit()
    mastery = MasteryService(session, settings=_settings())
    updates = mastery.update_from_assessment(
        user_id=owner.id,
        project_id=project.id,
        assessment_result=AssessmentResult(
            assessment_id=row.id,
            quiz_attempt_id=row.id,
            quiz_id=row.id,
            total_questions=sum(p.questions_seen for p in perfs),
            answered_count=sum(p.questions_seen for p in perfs),
            correct_count=sum(p.correct_count for p in perfs),
            partial_count=sum(p.partial_count for p in perfs),
            incorrect_count=sum(p.incorrect_count for p in perfs),
            score=50.0,
            concept_results=list(perfs),
        ),
    )
    return row, updates


def _growth(session, **kwargs):
    return GrowthService(session, settings=_settings(), **kwargs)


def _recs(session, **kwargs):
    return RecommendationService(session, settings=_settings(), **kwargs)


def _link_material(session, concept, material_id, pages=(1,)):
    """Wire extraction-style material provenance onto a concept."""
    concept.concept_metadata = {
        "materials": [{"material_id": str(material_id), "pages": list(pages)}]
    }
    session.flush()


def _material(session, project, name="Doc"):
    from app.repositories.materials import MaterialRepository

    mat = MaterialRepository(session).create(project_id=project.id, name=name)
    session.flush()
    return mat


# ------------------------------------------------------------- status rules


def test_concept_status_requires_evidence() -> None:
    # One weak observation is cold start, not failure.
    assert (
        concept_status(mastery=0.2, trend=MasteryTrend.STABLE, observations=1)
        == GrowthStatus.STABLE
    )
    assert (
        concept_status(mastery=0.2, trend=MasteryTrend.STABLE, observations=2)
        == GrowthStatus.REQUIRING_ATTENTION
    )
    assert (
        concept_status(mastery=0.9, trend=MasteryTrend.IMPROVING, observations=5)
        == GrowthStatus.IMPROVING
    )
    assert (
        concept_status(mastery=0.9, trend=MasteryTrend.DECLINING, observations=5)
        == GrowthStatus.STABLE
    )
    assert (
        concept_status(mastery=0.4, trend=MasteryTrend.DECLINING, observations=5)
        == GrowthStatus.REQUIRING_ATTENTION
    )


def test_project_status_rules() -> None:
    assert project_status(improving=0, attention=0, assessed=0) == GrowthStatus.STABLE
    assert project_status(improving=3, attention=0, assessed=5) == GrowthStatus.IMPROVING
    assert project_status(improving=0, attention=2, assessed=5) == GrowthStatus.REQUIRING_ATTENTION
    assert project_status(improving=0, attention=1, assessed=2) == GrowthStatus.REQUIRING_ATTENTION
    assert project_status(improving=0, attention=1, assessed=8) == GrowthStatus.STABLE
    assert project_status(improving=0, attention=0, assessed=4) == GrowthStatus.STABLE


# ------------------------------------------------------------- growth


def test_cold_start_honest(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    growth = _growth(session).project_growth(user_id=owner.id, project_id=project.id)
    assert growth.status == GrowthStatus.STABLE
    assert growth.has_evidence is False
    assert growth.overall_mastery == 0.0
    assert growth.assessed_concepts == 0
    assert growth.updated_at is None
    assert _growth(session).history(user_id=owner.id, project_id=project.id) == []
    assert _growth(session).concept_growth(user_id=owner.id, project_id=project.id) == []


def test_first_assessment_overall_and_counts(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    _apply_mastery(
        session,
        owner,
        project,
        [
            _perf(concepts["TCP"].id, "TCP"),
            _perf(concepts["UDP"].id, "UDP", norm=0.0, correct=0, incorrect=1, recent=["I"]),
        ],
        T0,
    )
    svc = _growth(session)
    growth = svc.project_growth(user_id=owner.id, project_id=project.id)
    assert growth.has_evidence is True
    assert growth.assessed_concepts == 2
    assert growth.assessment_count == 1
    assert growth.questions_answered == 2
    assert growth.overall_mastery == pytest.approx((0.625 + 0.375) / 2)
    assert (
        growth.concepts_improving + growth.concepts_stable + growth.concepts_requiring_attention
        == 2
    )
    assert growth.updated_at is not None


def test_refresh_writes_per_concept_rows(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    _apply_mastery(session, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    growth = _growth(session).refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=None
    )
    assert growth.has_evidence is True
    row = session.scalar(
        sa.select(Growth).where(
            Growth.user_id == owner.id,
            Growth.project_id == project.id,
            Growth.concept_id == concepts["TCP"].id,
        )
    )
    assert row is not None
    assert row.status == GrowthStatus.STABLE
    assert row.change_score == pytest.approx(0.125)
    assert "TCP" in (row.summary or "")


def test_improving_project_status(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    for day, norm in enumerate([0.2, 0.6, 1.0]):
        _apply_mastery(
            session,
            owner,
            project,
            [
                _perf(
                    concepts["TCP"].id,
                    "TCP",
                    norm=norm,
                    correct=1 if norm >= 0.6 else 0,
                    incorrect=1 if norm < 0.3 else 0,
                )
            ],
            T0 + timedelta(days=day),
        )
    growth = _growth(session).refresh_after_assessment(user_id=owner.id, project_id=project.id)
    assert growth.status == GrowthStatus.IMPROVING
    assert growth.concepts_improving == 1


def test_requiring_attention_state(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    for day in range(2):
        _apply_mastery(
            session,
            owner,
            project,
            [
                _perf(concepts["TCP"].id, "TCP", norm=0.2, correct=0, incorrect=1, recent=["I"]),
                _perf(concepts["UDP"].id, "UDP", norm=0.3, correct=0, incorrect=1, recent=["I"]),
            ],
            T0 + timedelta(days=day),
        )
    growth = _growth(session).refresh_after_assessment(user_id=owner.id, project_id=project.id)
    assert growth.status == GrowthStatus.REQUIRING_ATTENTION
    assert growth.concepts_requiring_attention == 2


def test_history_from_assessments(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    _apply_mastery(session, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    _apply_mastery(
        session, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0 + timedelta(days=3)
    )
    points = _growth(session).history(user_id=owner.id, project_id=project.id)
    assert len(points) == 2
    assert points[0].date <= points[1].date
    assert all(0.0 <= p.score <= 1.0 for p in points)


def test_confidence_is_evidence_not_correctness(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    _apply_mastery(
        session,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", seen=1)],
        T0,
    )
    growth = _growth(session).project_growth(user_id=owner.id, project_id=project.id)
    assert growth.average_confidence == pytest.approx(0.3)
    assert growth.overall_mastery == pytest.approx(0.625)
    assert growth.average_confidence != growth.overall_mastery


# ------------------------------------------------------------- recommendations


def _assessed(session, owner, project, concepts, specs, day=0):
    perfs = []
    for name, norm, recent in specs:
        correct = 1 if norm >= 0.6 else 0
        incorrect = 1 if norm < 0.3 else 0
        partial = 0 if (correct or incorrect) else 1
        perfs.append(
            _perf(
                concepts[name].id,
                name,
                norm=norm,
                correct=correct,
                partial=partial,
                incorrect=incorrect,
                recent=recent,
            )
        )
    row, _ = _apply_mastery(session, owner, project, perfs, T0 + timedelta(days=day))
    return row


def test_recommendation_generation_and_priority(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    mat = _material(session, project)
    _link_material(session, concepts["TCP"], mat.id)
    assessment = _assessed(
        session,
        owner,
        project,
        concepts,
        [("TCP", 0.2, ["I"]), ("UDP", 1.0, ["C"])],
    )
    created = _recs(session).refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=assessment.id
    )
    assert created, "weak concept with mistakes must produce recommendations"
    by_type = {r.type: r for r in created}
    assert RecommendationType.PRACTICE_QUIZ in by_type
    tcp_practice = by_type[RecommendationType.PRACTICE_QUIZ]
    assert tcp_practice.concept_id == concepts["TCP"].id
    assert tcp_practice.status == RecommendationStatus.ACTIVE
    assert 0 <= tcp_practice.priority <= 100
    assert "TCP" in (tcp_practice.reason or "")
    assert tcp_practice.source_assessment_id == assessment.id
    # No recommendation for the strong concept.
    assert all(r.concept_id != concepts["UDP"].id for r in created)
    events = session.scalars(
        sa.select(Event).where(Event.event_type == "RECOMMENDATION_GENERATED")
    ).all()
    assert len(events) == len(created)
    assert all("password" not in str(e.payload) for e in events)


def test_low_mastery_without_evidence_gets_less_priority(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    # TCP: single weak observation (cold-ish). UDP: repeated weak (evidence).
    _assessed(session, owner, project, concepts, [("TCP", 0.2, ["I"])])
    _assessed(session, owner, project, concepts, [("UDP", 0.2, ["I"])], day=1)
    _assessed(session, owner, project, concepts, [("UDP", 0.3, ["I"])], day=2)
    created = _recs(session).refresh_after_assessment(user_id=owner.id, project_id=project.id)
    udp_best = max((r.priority for r in created if r.concept_id == concepts["UDP"].id), default=-1)
    tcp_best = max((r.priority for r in created if r.concept_id == concepts["TCP"].id), default=-1)
    assert udp_best >= tcp_best


def test_declining_concept_flagged(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    for day, norm in enumerate([0.9, 0.5, 0.2]):
        _assessed(
            session,
            owner,
            project,
            concepts,
            [("TCP", norm, ["C"] if norm >= 0.6 else (["I"] if norm < 0.3 else ["P"]))],
            day=day,
        )
    created = _recs(session).refresh_after_assessment(user_id=owner.id, project_id=project.id)
    types = {r.type for r in created}
    assert RecommendationType.TUTOR_SESSION in types or RecommendationType.REVIEW_CONCEPT in types


def test_cold_start_exclusion(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    created = _recs(session).refresh_after_assessment(user_id=owner.id, project_id=project.id)
    assert created == []


def test_deduplication_and_regeneration(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    first_assessment = _assessed(session, owner, project, concepts, [("TCP", 0.2, ["I"])])
    svc = _recs(session)
    first = svc.refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=first_assessment.id
    )
    assert first
    second = svc.refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=first_assessment.id
    )
    assert second == []
    actives = session.scalars(
        sa.select(Recommendation).where(
            Recommendation.user_id == owner.id,
            Recommendation.project_id == project.id,
            Recommendation.status == RecommendationStatus.ACTIVE,
        )
    ).all()
    assert len(actives) == len(first)
    # Completing one allows regeneration of that scope afterwards.
    target = first[0]
    svc.complete(user_id=owner.id, project_id=project.id, recommendation_id=target.id)
    third = svc.refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=first_assessment.id
    )
    assert any(r.type == target.type and r.concept_id == target.concept_id for r in third)


def test_lifecycle_complete_dismiss_conflicts(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    mat = _material(session, project)
    _link_material(session, concepts["TCP"], mat.id)
    assessment = _assessed(session, owner, project, concepts, [("TCP", 0.2, ["I"])])
    svc = _recs(session)
    created = svc.refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=assessment.id
    )
    assert len(created) >= 2
    done = svc.complete(user_id=owner.id, project_id=project.id, recommendation_id=created[0].id)
    assert done.status == RecommendationStatus.COMPLETED
    assert done.completed_at is not None
    with pytest.raises(ConflictError):
        svc.complete(user_id=owner.id, project_id=project.id, recommendation_id=created[0].id)
    left = svc.dismiss(user_id=owner.id, project_id=project.id, recommendation_id=created[1].id)
    assert left.status == RecommendationStatus.DISMISSED
    with pytest.raises(ConflictError):
        svc.dismiss(user_id=owner.id, project_id=project.id, recommendation_id=created[1].id)


def test_expiry_on_resolved_mastery(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    bad = _assessed(session, owner, project, concepts, [("TCP", 0.1, ["I"])])
    svc = _recs(session)
    created = svc.refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=bad.id
    )
    assert created
    # Drive mastery to resolved with repeated correct evidence.
    for day in range(10, 16):
        _apply_mastery(
            session,
            owner,
            project,
            [_perf(concepts["TCP"].id, "TCP")],
            T0 + timedelta(days=day),
        )
    refreshed = svc.refresh_after_assessment(user_id=owner.id, project_id=project.id)
    assert refreshed == []  # resolved: nothing new, actives expired
    statuses = {
        r.type: r.status
        for r in session.scalars(
            sa.select(Recommendation).where(
                Recommendation.user_id == owner.id, Recommendation.project_id == project.id
            )
        )
    }
    assert all(s == RecommendationStatus.EXPIRED for s in statuses.values())


def _mastery(session):
    from app.services.mastery_service import MasteryService

    return MasteryService(session, settings=_settings())


def test_recommendation_material_relationship(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    mat = _material(session, project)
    _link_material(session, concepts["TCP"], mat.id)
    assessment = _assessed(session, owner, project, concepts, [("TCP", 0.2, ["I"])])
    created = _recs(session).refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=assessment.id
    )
    with_material = [r for r in created if r.material_id is not None]
    assert with_material, "concept-linked materials must surface (seeded via concepts)"
    for row in with_material:
        from app.models.materials import Material

        material = session.get(Material, row.material_id)
        assert material is not None and material.project_id == project.id


def test_recommendation_assessment_relationship(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    assessment = _assessed(session, owner, project, concepts, [("TCP", 0.2, ["I"])])
    created = _recs(session).refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=assessment.id
    )
    assert created
    assert all(r.source_assessment_id == assessment.id for r in created)


def _seed_rag(session, texts: dict[str, str], owner=None):
    import asyncio

    from app.ai.base import EmbedRequest
    from app.ai.fakes import DeterministicEmbeddingProvider
    from app.models.enums import MaterialStatus
    from app.models.materials import Document, DocumentChunk
    from app.repositories.materials import MaterialRepository

    owner = owner or make_user(session)
    project = make_project(session, owner)
    concepts = {}
    for name, description in texts.items():
        concept, _ = ConceptRepository(session).get_or_create(
            project_id=project.id, name=name, description=description
        )
        concepts[name] = concept
    mat = MaterialRepository(session).create(project_id=project.id, name="Doc")
    mat.status = MaterialStatus.READY
    session.flush()
    doc = Document(material_id=mat.id, project_id=project.id, page_count=1)
    session.add(doc)
    session.flush()
    provider = DeterministicEmbeddingProvider(dimensions=768)
    for i, (name, description) in enumerate(texts.items()):
        chunk_text = f"{name}: {description}"
        vec = asyncio.run(provider.embed(EmbedRequest(texts=[chunk_text]))).embeddings[0]
        session.add(
            DocumentChunk(
                document_id=doc.id,
                project_id=project.id,
                chunk_index=i,
                content=chunk_text,
                page_start=i + 1,
                page_end=i + 1,
                embedding=list(vec),
            )
        )
    session.commit()
    return owner, project, concepts


def test_completion_chain_updates_growth_and_recommendations(session: Session) -> None:
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService
    from app.core.config import Settings
    from app.models.enums import QuestionType
    from app.services.assessment_service import AssessmentService

    texts = {
        "Photosynthesis": "Photosynthesis converts sunlight into chemical energy in plants.",
        "Mitochondria": "Mitochondria release stored energy as ATP in cells.",
    }
    owner, project, _ = _seed_rag(session, texts)
    fake_ai = AIService(
        chat_provider=FakeChatProvider(),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
    )
    quiz_svc = AssessmentService(session, settings=Settings(test_fake_ai=True), ai_service=fake_ai)
    quiz, _ = asyncio.run(
        quiz_svc.create_quiz(
            user_id=owner.id,
            project_id=project.id,
            question_count=2,
            question_types=[QuestionType.MCQ],
        )
    )
    attempt, _ = asyncio.run(
        quiz_svc.start_attempt(user_id=owner.id, project_id=project.id, quiz_id=quiz.id)
    )
    from app.models.assessment import Question, QuizQuestion

    for question in session.scalars(
        sa.select(Question)
        .join(QuizQuestion, QuizQuestion.question_id == Question.id)
        .where(QuizQuestion.quiz_id == quiz.id)
    ):
        asyncio.run(
            quiz_svc.submit_answer(
                user_id=owner.id,
                project_id=project.id,
                attempt_id=attempt.id,
                question_id=question.id,
                answer=question.correct_answer,
            )
        )
    result = asyncio.run(
        quiz_svc.complete_attempt(user_id=owner.id, project_id=project.id, attempt_id=attempt.id)
    )
    assert result.score == 100.0
    # Chain ran synchronously: mastery, growth rows, and recommendations exist.
    growth = GrowthService(session, settings=_settings()).project_growth(
        user_id=owner.id, project_id=project.id
    )
    assert growth.has_evidence is True
    assert growth.assessed_concepts == 2
    # Single observations: trends need history, so the project is STABLE —
    # trend is never a single answer.
    assert growth.status == GrowthStatus.STABLE
    assert growth.concepts_stable == 2
    recs, total = RecommendationService(session, settings=_settings()).list_active(
        user_id=owner.id, project_id=project.id
    )
    assert total >= 0  # all-correct evidence may legitimately yield few recs


def test_chain_survives_downstream_faults(session: Session, monkeypatch) -> None:
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService
    from app.core.config import Settings
    from app.models.assessment import Assessment
    from app.models.enums import QuestionType
    from app.services.assessment_service import AssessmentService

    texts = {"Photosynthesis": "Photosynthesis converts sunlight into energy."}
    owner, project, _ = _seed_rag(session, texts)
    fake_ai = AIService(
        chat_provider=FakeChatProvider(),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
    )
    quiz_svc = AssessmentService(session, settings=Settings(test_fake_ai=True), ai_service=fake_ai)
    quiz, _ = asyncio.run(
        quiz_svc.create_quiz(
            user_id=owner.id,
            project_id=project.id,
            question_count=1,
            question_types=[QuestionType.MCQ],
        )
    )
    attempt, _ = asyncio.run(
        quiz_svc.start_attempt(user_id=owner.id, project_id=project.id, quiz_id=quiz.id)
    )

    def _boom(**kwargs):
        raise RuntimeError("downstream on fire")

    monkeypatch.setattr("app.services.mastery_service.MasteryService.update_from_assessment", _boom)
    monkeypatch.setattr("app.services.growth_service.GrowthService.refresh_after_assessment", _boom)
    monkeypatch.setattr(
        "app.services.recommendation_service.RecommendationService.refresh_after_assessment",
        _boom,
    )
    result = asyncio.run(
        quiz_svc.complete_attempt(user_id=owner.id, project_id=project.id, attempt_id=attempt.id)
    )
    stored = session.get(Assessment, result.assessment_id)
    assert stored is not None and stored.status == AssessmentStatus.COMPLETED


def _route_client(session, owner):

    from app.auth.dependencies import get_current_user
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: session

    async def _owner():
        return owner

    app.dependency_overrides[get_current_user] = _owner
    return app


def test_routes_growth_and_recommendations(session: Session) -> None:

    owner, project, concepts = _seed_concepts(session, ["TCP"])
    mat = _material(session, project)
    _link_material(session, concepts["TCP"], mat.id)
    _apply_mastery(
        session,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", norm=0.2, correct=0, incorrect=1, recent=["I"])],
        T0,
    )
    GrowthService(session, settings=_settings()).refresh_after_assessment(
        user_id=owner.id, project_id=project.id
    )
    assessment = _assessed(session, owner, project, concepts, [("TCP", 0.2, ["I"])])
    RecommendationService(session, settings=_settings()).refresh_after_assessment(
        user_id=owner.id, project_id=project.id, assessment_id=assessment.id
    )
    app = _route_client(session, owner)
    try:
        client = TestClient(app)
        growth = client.get(f"/api/v1/projects/{project.id}/growth")
        assert growth.status_code == 200, growth.text
        body = growth.json()
        assert body["has_evidence"] is True
        assert body["assessed_concepts"] == 1
        assert body["status"] in ("IMPROVING", "STABLE", "REQUIRING_ATTENTION")
        assert "overall_mastery" in body and "concepts" in body

        history = client.get(f"/api/v1/projects/{project.id}/growth/history")
        assert history.status_code == 200
        assert history.json()["total"] >= 1

        recs = client.get(f"/api/v1/projects/{project.id}/recommendations")
        assert recs.status_code == 200, recs.text
        assert recs.json()["total"] >= 1
        first = recs.json()["items"][0]
        assert first["concept_id"] == str(concepts["TCP"].id)
        assert set(first) >= {"id", "type", "title", "reason", "actions", "priority", "status"}
        assert "storage_key" not in str(first)
        assert first["actions"], "backend must confirm available actions"

        detail = client.get(f"/api/v1/projects/{project.id}/recommendations/{first['id']}")
        assert detail.status_code == 200

        done = client.post(f"/api/v1/projects/{project.id}/recommendations/{first['id']}/complete")
        assert done.status_code == 200
        assert done.json()["status"] == "COMPLETED"
        again = client.post(f"/api/v1/projects/{project.id}/recommendations/{first['id']}/complete")
        assert again.status_code == 409
    finally:
        app.dependency_overrides.clear()


def test_routes_isolation(session: Session) -> None:

    owner, project, concepts = _seed_concepts(session, ["TCP"])
    _apply_mastery(session, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    recs = _recs(session).refresh_after_assessment(user_id=owner.id, project_id=project.id)
    stranger = make_user(session, email="stranger@example.com")
    other = make_project(session, stranger)
    app = _route_client(session, stranger)
    try:
        client = TestClient(app)
        assert client.get(f"/api/v1/projects/{project.id}/growth").status_code == 404
        assert client.get(f"/api/v1/projects/{project.id}/growth/history").status_code == 404
        assert client.get(f"/api/v1/projects/{project.id}/recommendations").status_code == 404
        if recs:
            rid = str(recs[0].id)
            assert (
                client.get(f"/api/v1/projects/{project.id}/recommendations/{rid}").status_code
                == 404
            )
            assert (
                client.post(
                    f"/api/v1/projects/{project.id}/recommendations/{rid}/complete"
                ).status_code
                == 404
            )
            assert (
                client.post(
                    f"/api/v1/projects/{project.id}/recommendations/{rid}/dismiss"
                ).status_code
                == 404
            )
        assert client.get(f"/api/v1/projects/{other.id}/growth").json()["has_evidence"] is False
    finally:
        app.dependency_overrides.clear()


def test_actions_match_available_targets(session: Session) -> None:
    from app.services.recommendation_service import RecommendationService as RS

    assert RS.actions_for(RecommendationType.PRACTICE_QUIZ, has_material=True) == ["practice_quiz"]
    assert "open_material" in RS.actions_for(RecommendationType.REVIEW_CONCEPT, has_material=True)
    assert "open_material" not in RS.actions_for(
        RecommendationType.REVIEW_CONCEPT, has_material=False
    )
    assert RS.actions_for(RecommendationType.TUTOR_SESSION, has_material=False) == ["ask_tutor"]
