"""Mastery Engine: deterministic algorithm, persistence, API, integrations."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.models.assessment import Assessment
from app.models.enums import AssessmentStatus, MasteryTrend, QuestionType
from app.models.intelligence import Mastery, MasteryHistory
from app.models.materials import Document, DocumentChunk
from app.models.ops import Event
from app.repositories.assessments import AssessmentRepository
from app.repositories.intelligence import MasteryRepository
from app.repositories.knowledge import ConceptRepository
from app.repositories.materials import MaterialRepository
from app.services.assessment_contracts import AssessmentResult, ConceptPerformance
from app.services.mastery_service import MasteryService
from tests.conftest import make_project, make_user

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _settings(**kwargs) -> Settings:
    kwargs.setdefault("test_fake_ai", True)
    return Settings(**kwargs)


def _mastery(session: Session, **kwargs) -> MasteryService:
    return MasteryService(session, settings=_settings())


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


def _manual_assessment(session, owner, project, perfs, completed_at):
    """Persisted immutable assessment row (no quiz needed) + mirror result."""
    repo = AssessmentRepository(session)
    row = repo.create(project_id=project.id, user_id=owner.id, quiz_attempt_id=None)
    row.status = AssessmentStatus.COMPLETED
    row.score = 50.0
    row.completed_at = completed_at
    row.concept_results = [p.as_dict() for p in perfs]
    session.commit()
    return row, AssessmentResult(
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
    )


def _apply(session, svc, owner, project, perfs, completed_at):
    row, result = _manual_assessment(session, owner, project, perfs, completed_at)
    updates = svc.update_from_assessment(
        user_id=owner.id, project_id=project.id, assessment_result=result
    )
    return row, result, updates


def _row(session, owner, project, concept):
    return MasteryRepository(session).get_for_user(
        user_id=owner.id, project_id=project.id, concept_id=concept.id
    )


# ------------------------------------------------------------- algorithm


def test_cold_start_correct(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    _, _, updates = _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    assert len(updates) == 1
    update = updates[0]
    assert update.previous_score == 0.5
    assert update.new_score == 0.625
    assert update.confidence == 0.3
    row = _row(session, owner, project, concepts["TCP"])
    assert row is not None
    assert row.score == 62.5  # stored 0-100
    assert row.confidence == 0.3
    assert row.trend == MasteryTrend.STABLE
    history = MasteryRepository(session).history_for_mastery(row.id)
    assert len(history) == 1
    assert history[0].previous_score == 50.0
    assert history[0].score == 62.5
    assert history[0].assessment_id is not None


def test_cold_start_incorrect_and_partial(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    svc = _mastery(session)
    _, _, updates = _apply(
        session,
        svc,
        owner,
        project,
        [
            _perf(concepts["TCP"].id, "TCP", norm=0.0, correct=0, incorrect=1, recent=["I"]),
            _perf(concepts["UDP"].id, "UDP", norm=0.5, correct=0, partial=1, recent=["P"]),
        ],
        T0,
    )
    by_concept = {u.concept_id: u for u in updates}
    assert by_concept[concepts["TCP"].id].new_score == 0.375
    # Partial evidence from baseline holds steady without collapsing either way.
    assert by_concept[concepts["UDP"].id].new_score == 0.5


def test_repeated_correct_diminishing(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    scores = []
    for day in range(3):
        _, _, updates = _apply(
            session,
            svc,
            owner,
            project,
            [_perf(concepts["TCP"].id, "TCP")],
            T0 + timedelta(days=day),
        )
        scores.append(updates[0].new_score)
    assert scores == sorted(scores)  # monotonic improvement
    deltas = [b - a for a, b in zip(scores, scores[1:])]  # noqa: B905 - pairwise deltas
    assert deltas[0] > deltas[1] > 0  # diminishing influence
    assert all(0.0 <= s <= 1.0 for s in scores)


def test_not_latest_score_replacement(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    _, _, first = _apply(
        session,
        svc,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", norm=0.9)],
        T0,
    )
    assert first[0].new_score == pytest.approx(0.6)
    _, _, second = _apply(
        session,
        svc,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", norm=0.4, correct=0, incorrect=1, recent=["I"])],
        T0 + timedelta(days=1),
    )
    # History tempers the drop: nowhere near the latest 0.40. (0.5446, not
    # 0.5460: the 1-day recency decay pulls the prior toward baseline first.)
    assert second[0].new_score == pytest.approx(0.5446, abs=0.001)
    assert abs(second[0].new_score - 0.4) > 0.1


def test_improvement_without_instant_perfection(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    _, _, first = _apply(
        session,
        svc,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", norm=0.4, correct=0, incorrect=1, recent=["I"])],
        T0,
    )
    assert first[0].new_score < 0.5
    _, _, second = _apply(
        session,
        svc,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", norm=0.9)],
        T0 + timedelta(days=1),
    )
    assert 0.5 < second[0].new_score < 0.75


def test_confidence_grows_with_diminishing_returns(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    confs = []
    for day in range(6):
        _, _, updates = _apply(
            session,
            svc,
            owner,
            project,
            [_perf(concepts["TCP"].id, "TCP", seen=2)],
            T0 + timedelta(days=day),
        )
        confs.append(updates[0].confidence)
    assert confs == sorted(confs)
    assert all(0.0 <= c <= 1.0 for c in confs)
    gains = [b - a for a, b in zip(confs, confs[1:])]  # noqa: B905 - pairwise deltas
    assert all(g > 0 for g in gains)
    assert gains[0] > gains[-1]
    # One observation is far less confident than many.
    assert confs[0] < 0.5 < confs[-1]


def test_time_decay_pulls_toward_baseline(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    _, _, updates = _apply(
        session,
        svc,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", norm=0.0, correct=0, incorrect=1, recent=["I"])],
        T0 + timedelta(days=60),
    )
    # 60-day decay (lambda 0.02 -> 0.301): prior .625 decays to ~.538, so the
    # miss lands at ~.392 — below the no-decay counterfactual .456.
    assert updates[0].new_score == pytest.approx(0.3924, abs=0.005)
    assert updates[0].new_score < 0.456
    # Confidence in the stale estimate decayed too.
    assert updates[0].confidence < 0.3


def test_trend_improving_declining_stable(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["Up", "Down", "Flat"])
    svc = _mastery(session)
    aid = concepts["Up"].id
    for day, norm in enumerate([0.2, 0.5, 0.9]):
        _apply(
            session,
            svc,
            owner,
            project,
            [
                _perf(
                    aid,
                    "Up",
                    norm=norm,
                    correct=1 if norm >= 0.6 else 0,
                    incorrect=1 if norm < 0.3 else 0,
                )
            ],
            T0 + timedelta(days=day),
        )
    assert _row(session, owner, project, concepts["Up"]).trend == MasteryTrend.IMPROVING
    did = concepts["Down"].id
    for day, norm in enumerate([0.9, 0.5, 0.1]):
        _apply(
            session,
            svc,
            owner,
            project,
            [
                _perf(
                    did,
                    "Down",
                    norm=norm,
                    correct=1 if norm >= 0.6 else 0,
                    incorrect=1 if norm < 0.3 else 0,
                )
            ],
            T0 + timedelta(days=day),
        )
    assert _row(session, owner, project, concepts["Down"]).trend == MasteryTrend.DECLINING
    fid = concepts["Flat"].id
    for day in range(3):
        _apply(
            session,
            svc,
            owner,
            project,
            [_perf(fid, "Flat", norm=0.5, correct=0, partial=1)],
            T0 + timedelta(days=day),
        )
    assert _row(session, owner, project, concepts["Flat"]).trend == MasteryTrend.STABLE


def test_bounds_hold_under_extremes(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["Hot", "Cold"])
    svc = _mastery(session)
    for day in range(30):
        _apply(
            session,
            svc,
            owner,
            project,
            [_perf(concepts["Hot"].id, "Hot")],
            T0 + timedelta(days=day),
        )
        _apply(
            session,
            svc,
            owner,
            project,
            [_perf(concepts["Cold"].id, "Cold", norm=0.0, correct=0, incorrect=1, recent=["I"])],
            T0 + timedelta(days=day),
        )
    hot = _row(session, owner, project, concepts["Hot"])
    cold = _row(session, owner, project, concepts["Cold"])
    assert 0.0 <= hot.score / 100 <= 1.0
    assert 0.0 <= cold.score / 100 <= 1.0
    assert 0.0 <= hot.confidence <= 1.0
    assert hot.score / 100 < 1.0  # asymptotically approaches, never reaches
    assert cold.score / 100 > 0.0


def test_determinism_same_inputs_same_outputs(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    first_updates = []
    for day, norm in enumerate([1.0, 0.5, 0.0]):
        _, _, updates = _apply(
            session,
            svc,
            owner,
            project,
            [_perf(concepts["TCP"].id, "TCP", norm=norm)],
            T0 + timedelta(days=day),
        )
        first_updates.append((updates[0].new_score, updates[0].confidence))
    assert _row(session, owner, project, concepts["TCP"]) is not None
    rebuilt = svc.rebuild_concept(
        user_id=owner.id, project_id=project.id, concept_id=concepts["TCP"].id
    )
    assert rebuilt is not None
    assert rebuilt.score / 100 == pytest.approx(first_updates[-1][0])
    assert rebuilt.confidence == pytest.approx(first_updates[-1][1])


# ------------------------------------------------------------- persistence


def test_history_previous_new_and_source(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    row, _, _ = _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    _, _, _ = _apply(
        session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0 + timedelta(days=1)
    )
    history = MasteryRepository(session).history_for_mastery(
        _row(session, owner, project, concepts["TCP"]).id
    )
    assert len(history) == 2
    assert history[0].previous_score == 50.0
    assert history[1].previous_score == history[0].score
    assert all(h.assessment_id is not None for h in history)
    assert all(h.source == "ASSESSMENT" for h in history)
    assert row.concept_results[0]["concept_name"] == "TCP"


def test_idempotent_double_apply(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    _, result, first = _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    second = svc.update_from_assessment(
        user_id=owner.id, project_id=project.id, assessment_result=result
    )
    assert second == []
    assert first[0].new_score == _row(session, owner, project, concepts["TCP"]).score / 100
    assert (
        MasteryRepository(session).history_count(_row(session, owner, project, concepts["TCP"]).id)
        == 1
    )


def test_transaction_rollback_on_bad_concept(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    row, _ = _manual_assessment(session, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    from app.services.assessment_contracts import AssessmentResult as AR

    result = AR(
        assessment_id=row.id,
        quiz_attempt_id=row.id,
        quiz_id=row.id,
        total_questions=2,
        answered_count=2,
        correct_count=2,
        partial_count=0,
        incorrect_count=0,
        score=100.0,
        concept_results=[
            _perf(concepts["TCP"].id, "TCP"),
            ConceptPerformance(
                concept_id=uuid.uuid4(),
                concept_name="Ghost",
                questions_seen=1,
                correct_count=1,
                normalized_score=1.0,
                recent=["C"],
            ),
        ],
    )
    with pytest.raises(NotFoundError):
        svc.update_from_assessment(
            user_id=owner.id, project_id=project.id, assessment_result=result
        )
    # All-or-nothing: the valid concept was rolled back too.
    assert _row(session, owner, project, concepts["TCP"]) is None


def test_only_assessed_concepts_update(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    svc = _mastery(session)
    _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    assert _row(session, owner, project, concepts["TCP"]) is not None
    assert _row(session, owner, project, concepts["UDP"]) is None


def test_assessment_record_unchanged(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    row, _, _ = _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    session.refresh(row)
    assert row.score == 50.0
    assert row.concept_results[0]["normalized_score"] == 1.0


def test_cross_project_concept_rejected(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    other = make_project(session, owner)
    foreign, _ = ConceptRepository(session).get_or_create(
        project_id=other.id, name="Foreign", description="Elsewhere."
    )
    session.commit()
    svc = _mastery(session)
    row, _ = _manual_assessment(session, owner, project, [_perf(foreign.id, "Foreign")], T0)
    from app.services.assessment_contracts import AssessmentResult as AR

    with pytest.raises(NotFoundError):
        svc.update_from_assessment(
            user_id=owner.id,
            project_id=project.id,
            assessment_result=AR(
                assessment_id=row.id,
                quiz_attempt_id=row.id,
                quiz_id=row.id,
                total_questions=1,
                answered_count=1,
                correct_count=1,
                partial_count=0,
                incorrect_count=0,
                score=100.0,
                concept_results=[_perf(foreign.id, "Foreign")],
            ),
        )


def test_history_unique_backstop(session: Session) -> None:
    import sqlalchemy.exc

    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    _, _, _ = _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    row = _row(session, owner, project, concepts["TCP"])
    history = MasteryRepository(session).history_for_mastery(row.id)
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        session.add(
            MasteryHistory(
                mastery_id=row.id,
                score=90.0,
                confidence=0.9,
                source="ASSESSMENT",
                assessment_id=history[0].assessment_id,
            )
        )
        session.flush()
    session.rollback()


# ------------------------------------------------------------- explanation


def test_explain_cold_start_and_evidence(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    cold = svc.explain(user_id=owner.id, project_id=project.id, concept_id=concepts["TCP"].id)
    assert cold.mastery_score == 0.5
    assert cold.confidence == 0.2
    assert cold.has_evidence is False
    assert cold.trend == MasteryTrend.STABLE
    assert cold.recent_performance == []
    assert cold.contributing_assessments == []

    _apply(
        session,
        svc,
        owner,
        project,
        [_perf(concepts["TCP"].id, "TCP", norm=0.8, recent=["C"])],
        T0,
    )
    full = svc.explain(user_id=owner.id, project_id=project.id, concept_id=concepts["TCP"].id)
    assert full.has_evidence is True
    assert full.mastery_score == pytest.approx(0.575)
    assert full.evidence_assessments == 1
    assert full.evidence_questions == 1
    assert full.recent_performance == ["C"]
    assert len(full.contributing_assessments) == 1


def test_explain_unknown_concept_404(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    with pytest.raises(NotFoundError):
        svc.explain(user_id=owner.id, project_id=project.id, concept_id=uuid.uuid4())


# ------------------------------------------------------------- API


def _client(session, owner):

    from app.auth.dependencies import get_current_user
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: session

    async def _owner():
        return owner

    app.dependency_overrides[get_current_user] = _owner
    return app


def test_api_list_detail_history(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    svc = _mastery(session)
    _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    _apply(
        session,
        svc,
        owner,
        project,
        [_perf(concepts["UDP"].id, "UDP", norm=0.0, correct=0, incorrect=1, recent=["I"])],
        T0,
    )
    app = _client(session, owner)
    try:
        from fastapi.testclient import TestClient as _TestClient

        client = _TestClient(app)
        listed = client.get(f"/api/v1/projects/{project.id}/mastery?page_size=1")
        assert listed.status_code == 200, listed.text
        body = listed.json()
        assert body["total"] == 2
        assert len(body["items"]) == 1
        # Lowest-first default: UDP (0.375) before TCP (0.625).
        assert body["items"][0]["concept_name"] == "UDP"

        by_name = client.get(f"/api/v1/projects/{project.id}/mastery?sort=name&page_size=50").json()
        assert [i["concept_name"] for i in by_name["items"]] == ["TCP", "UDP"]

        detail = client.get(f"/api/v1/projects/{project.id}/mastery/{concepts['TCP'].id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["mastery_score"] == pytest.approx(0.625)
        assert detail.json()["has_evidence"] is True
        assert detail.json()["evidence_questions"] == 1

        # Cold-start concept: baseline, explicitly unevidenced (never 0%).
        cold_concept, _ = ConceptRepository(session).get_or_create(
            project_id=project.id, name="Cold", description="Unassessed."
        )
        session.commit()
        cold = client.get(f"/api/v1/projects/{project.id}/mastery/{cold_concept.id}")
        assert cold.status_code == 200
        assert cold.json()["mastery_score"] == 0.5
        assert cold.json()["has_evidence"] is False

        history = client.get(f"/api/v1/projects/{project.id}/mastery/{concepts['TCP'].id}/history")
        assert history.status_code == 200
        rows = history.json()["items"]
        assert len(rows) == 1
        assert rows[0]["previous_score"] == 0.5
        assert rows[0]["new_score"] == pytest.approx(0.625)
        assert rows[0]["assessment_id"] is not None

        assert (
            client.get(f"/api/v1/projects/{project.id}/mastery/{uuid.uuid4()}").status_code == 404
        )
    finally:
        app.dependency_overrides.clear()


def test_api_no_write_endpoints(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    app = _client(session, owner)
    try:
        from fastapi.testclient import TestClient as _TestClient

        client = _TestClient(app)
        assert client.post(f"/api/v1/projects/{project.id}/mastery", json={}).status_code == 405
        assert client.put(f"/api/v1/projects/{project.id}/mastery", json={}).status_code == 405
        assert (
            client.delete(f"/api/v1/projects/{project.id}/mastery/{uuid.uuid4()}").status_code
            == 405
        )
    finally:
        app.dependency_overrides.clear()


def _seed_rag(session, texts: dict[str, str], owner=None):
    """Concepts + READY material with exact-query chunks (mirrors quiz tests)."""
    from app.ai.base import EmbedRequest
    from app.ai.fakes import DeterministicEmbeddingProvider
    from app.models.enums import MaterialStatus

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


def test_completion_drives_mastery_end_to_end(session: Session) -> None:
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService
    from app.core.config import Settings
    from app.services.assessment_service import AssessmentService

    texts = {
        "Photosynthesis": "Photosynthesis converts sunlight into chemical energy in plants.",
        "Mitochondria": "Mitochondria release stored energy as ATP in cells.",
    }
    owner, project, concepts = _seed_rag(session, texts)
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
    from app.models.assessment import Question as QuestionModel
    from app.models.assessment import QuizQuestion as QuizQuestionModel

    questions = session.scalars(
        sa.select(QuestionModel)
        .join(QuizQuestionModel, QuizQuestionModel.question_id == QuestionModel.id)
        .where(QuizQuestionModel.quiz_id == quiz.id)
    ).all()
    for question in questions:
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
    # Mastery followed automatically for assessed concepts only.
    mastery_svc = _mastery(session)
    estimates = mastery_svc.scores_for_concepts(
        user_id=owner.id,
        project_id=project.id,
        concept_ids=[c.id for c in concepts.values()],
    )
    assert set(estimates) == {c.id for c in concepts.values()}
    assert all(v == pytest.approx(0.625) for v in estimates.values())
    events = session.execute(
        sa.select(sa.func.count())
        .select_from(Event)
        .where(Event.event_type == "MASTERY_UPDATED", Event.project_id == project.id)
    ).scalar()
    assert events == 2
    # The assessment record itself is untouched by the mastery write.
    stored = session.get(Assessment, result.assessment_id)
    assert stored is not None and stored.score == 100.0


def test_duplicate_completion_never_duplicates_mastery(session: Session) -> None:
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService
    from app.core.config import Settings
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
    asyncio.run(
        quiz_svc.complete_attempt(user_id=owner.id, project_id=project.id, attempt_id=attempt.id)
    )
    before = MasteryRepository(session).history_counts(
        [
            m.id
            for m in session.scalars(
                sa.select(Mastery).where(
                    Mastery.project_id == project.id, Mastery.user_id == owner.id
                )
            )
        ]
    )
    with pytest.raises(ConflictError):
        asyncio.run(
            quiz_svc.complete_attempt(
                user_id=owner.id, project_id=project.id, attempt_id=attempt.id
            )
        )
    after = MasteryRepository(session).history_counts(
        [
            m.id
            for m in session.scalars(
                sa.select(Mastery).where(
                    Mastery.project_id == project.id, Mastery.user_id == owner.id
                )
            )
        ]
    )
    assert before == after


def test_completion_survives_mastery_failure(session: Session, monkeypatch) -> None:
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService
    from app.core.config import Settings
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
        raise RuntimeError("mastery store on fire")

    monkeypatch.setattr("app.services.mastery_service.MasteryService.update_from_assessment", _boom)
    result = asyncio.run(
        quiz_svc.complete_attempt(user_id=owner.id, project_id=project.id, attempt_id=attempt.id)
    )
    assert result.total_questions == 1
    stored = session.get(Assessment, result.assessment_id)
    assert stored is not None and stored.status == AssessmentStatus.COMPLETED
    assert (
        session.scalar(
            sa.select(sa.func.count(Mastery.id)).where(
                Mastery.project_id == project.id, Mastery.user_id == owner.id
            )
        )
        == 0
    )


def test_real_mastery_shapes_next_quiz(session: Session) -> None:
    """Persisted mastery (no attempts at all) shifts quiz concept emphasis."""
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService
    from app.core.config import Settings
    from app.services.assessment_service import AssessmentService

    texts = {
        "Aaa": "Aaa concepts explain alpha foundations clearly stated here.",
        "Bbb": "Bbb concepts explain beta foundations clearly stated here.",
    }
    owner, project, concepts = _seed_rag(session, texts)
    mastery_svc = _mastery(session)
    _apply(
        session,
        mastery_svc,
        owner,
        project,
        [_perf(concepts["Aaa"].id, "Aaa")],
        T0,
    )
    _apply(
        session,
        mastery_svc,
        owner,
        project,
        [_perf(concepts["Bbb"].id, "Bbb", norm=0.0, correct=0, incorrect=1, recent=["I"])],
        T0,
    )
    fake_ai = AIService(
        chat_provider=FakeChatProvider(),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
    )
    quiz_svc = AssessmentService(session, settings=Settings(test_fake_ai=True), ai_service=fake_ai)
    quiz, _ = asyncio.run(
        quiz_svc.create_quiz(
            user_id=owner.id,
            project_id=project.id,
            question_count=3,
            question_types=[QuestionType.MCQ],
        )
    )
    counts: dict = {}
    for view in quiz_svc.quiz_questions_view(quiz.id):
        for concept in view["concepts"]:
            counts[concept["name"]] = counts.get(concept["name"], 0) + 1
    # Low-mastery Bbb (0.375) outweighs high-mastery Aaa (0.625): 2 to 1.
    assert counts.get("Bbb") == 2
    assert counts.get("Aaa") == 1


def test_tutor_context_uses_relevant_mastery(session: Session) -> None:
    from app.core.config import Settings
    from app.services.tutor_service import QuestionKind, TutorService

    texts = {
        "Photosynthesis": "Photosynthesis converts sunlight into chemical energy in plants.",
        "Mitochondria": "Mitochondria release stored energy as ATP in cells.",
    }
    owner, project, concepts = _seed_rag(session, texts)
    _apply(
        session,
        _mastery(session),
        owner,
        project,
        [_perf(concepts["Photosynthesis"].id, "Photosynthesis")],
        T0,
    )
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService

    tutor = TutorService(
        session,
        settings=Settings(test_fake_ai=True),
        ai_service=AIService(
            chat_provider=FakeChatProvider(),
            embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
        ),
    )
    context = asyncio.run(
        tutor._assemble_context(
            user_id=owner.id,
            project=project,
            kind=QuestionKind.PROJECT_GROUNDED,
            question="Photosynthesis converts sunlight into energy, explain please.",
            history=[],
        )
    )
    assert context.mastery_estimates.get("Photosynthesis") == pytest.approx(0.625)
    assert set(context.mastery_estimates) <= set(context.concepts)
    from app.ai.prompts import build_tutor_prompt

    _, user_prompt = build_tutor_prompt(
        project_name="P",
        learning_goal=None,
        target_outcome=None,
        difficulty=None,
        concepts=["Photosynthesis"],
        history=[],
        evidence_text="e",
        has_evidence=True,
        question="q",
        mastery=context.mastery_estimates,
    )
    assert "- Photosynthesis: 0.62" in user_prompt


def test_tutor_survives_mastery_faults(session: Session, monkeypatch) -> None:
    from app.ai.fakes import DeterministicEmbeddingProvider, FakeChatProvider
    from app.ai.service import AIService
    from app.core.config import Settings
    from app.services.tutor_service import TutorService

    texts = {"Photosynthesis": "Photosynthesis converts sunlight into energy."}
    owner, project, _ = _seed_rag(session, texts)

    def _boom(**kwargs):
        raise RuntimeError("mastery unavailable")

    monkeypatch.setattr("app.services.mastery_service.MasteryService.scores_for_concepts", _boom)
    tutor = TutorService(
        session,
        settings=Settings(test_fake_ai=True),
        ai_service=AIService(
            chat_provider=FakeChatProvider(),
            embedding_provider=DeterministicEmbeddingProvider(dimensions=768),
        ),
    )
    conv = tutor.create_conversation(user_id=owner.id, project_id=project.id)
    exchange = asyncio.run(
        tutor.send_message(
            user_id=owner.id,
            project_id=project.id,
            conversation_id=conv.id,
            content="Explain photosynthesis in general terms please.",
        )
    )
    assert exchange.assistant_message.content


def test_api_isolation(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    svc = _mastery(session)
    _apply(session, svc, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    stranger = make_user(session, email="stranger@example.com")
    other = make_project(session, stranger)
    app = _client(session, stranger)
    try:
        from fastapi.testclient import TestClient

        client = TestClient(app)
        # B cannot see A's project mastery at all (404, never 403).
        assert client.get(f"/api/v1/projects/{project.id}/mastery").status_code == 404
        assert (
            client.get(f"/api/v1/projects/{project.id}/mastery/{concepts['TCP'].id}").status_code
            == 404
        )
        assert (
            client.get(
                f"/api/v1/projects/{project.id}/mastery/{concepts['TCP'].id}/history"
            ).status_code
            == 404
        )
        # B's own project is simply empty.
        assert client.get(f"/api/v1/projects/{other.id}/mastery").json()["items"] == []
    finally:
        app.dependency_overrides.clear()
