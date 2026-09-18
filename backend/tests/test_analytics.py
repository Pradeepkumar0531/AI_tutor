"""Analytics + events: feed, dashboard aggregates, isolation, performance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.enums import EventType
from app.repositories.knowledge import ConceptRepository
from app.services.analytics_service import AnalyticsService
from app.services.assessment_contracts import AssessmentResult, ConceptPerformance
from app.services.event_service import EventService, sanitize_payload
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


def _complete(session, owner, project, perfs, completed_at, score=50.0):
    """Immutable completed assessment row + mirror result (no quiz needed)."""
    from app.models.enums import AssessmentStatus
    from app.repositories.assessments import AssessmentRepository
    from app.services.mastery_service import MasteryService

    repo = AssessmentRepository(session)
    row = repo.create(project_id=project.id, user_id=owner.id, quiz_attempt_id=None)
    row.status = AssessmentStatus.COMPLETED
    row.score = score
    row.completed_at = completed_at
    row.concept_results = [p.as_dict() for p in perfs]
    session.commit()
    result = AssessmentResult(
        assessment_id=row.id,
        quiz_attempt_id=row.id,
        quiz_id=row.id,
        total_questions=sum(p.questions_seen for p in perfs),
        answered_count=sum(p.questions_seen for p in perfs),
        correct_count=sum(p.correct_count for p in perfs),
        partial_count=sum(p.partial_count for p in perfs),
        incorrect_count=sum(p.incorrect_count for p in perfs),
        score=score,
        concept_results=list(perfs),
    )
    MasteryService(session, settings=_settings()).update_from_assessment(
        user_id=owner.id, project_id=project.id, assessment_result=result
    )
    return row, result


def _analytics(session: Session, **kwargs):
    return AnalyticsService(session, settings=_settings(), **kwargs)


def _events(session: Session, **kwargs):
    return EventService(session)


# ------------------------------------------------------------- event service


def test_event_record_validates_and_sanitizes(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    svc = _events(session)
    event = svc.record(
        event_type=EventType.QUIZ_STARTED,
        user_id=owner.id,
        project_id=project.id,
        entity_type="quiz",
        entity_id=uuid.uuid4(),
        payload={"quiz_id": "q", "password": "x", "answer": "y", "score": 3},
    )
    session.flush()
    assert event.id is not None
    assert event.payload == {"quiz_id": "q", "score": 3}
    with pytest.raises(BadRequestError):
        svc.record(event_type="NOPE", user_id=owner.id, project_id=project.id)
    with pytest.raises(BadRequestError):
        svc.record(
            event_type=EventType.QUIZ_STARTED,
            user_id=owner.id,
            project_id=project.id,
            payload=["not", "a", "dict"],  # type: ignore[arg-type]
        )
    with pytest.raises(NotFoundError):
        svc.record(event_type=EventType.QUIZ_STARTED, user_id=owner.id, project_id=uuid.uuid4())


def test_sanitize_keeps_ids_drops_content() -> None:
    assert sanitize_payload(None) is None
    clean = sanitize_payload(
        {"question_id": "q", "quiz_id": "z", "answer": "a", "prompt": "p", "score": 1}
    )
    assert clean == {"question_id": "q", "quiz_id": "z", "score": 1}


def test_event_feed_order_filter_pagination(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    svc = _events(session)
    first = svc.record(event_type=EventType.QUIZ_STARTED, user_id=owner.id, project_id=project.id)
    session.commit()
    second = svc.record(event_type=EventType.QUIZ_STARTED, user_id=owner.id, project_id=project.id)
    session.commit()
    third = svc.record(
        event_type=EventType.ASSESSMENT_COMPLETED, user_id=owner.id, project_id=project.id
    )
    session.commit()
    rows, total = svc.feed(user_id=owner.id, project_id=project.id)
    assert total == 4  # + PROJECT_CREATED from setup
    assert [r.id for r in rows][:3] == [third.id, second.id, first.id]
    filtered, total = svc.feed(
        user_id=owner.id, project_id=project.id, event_types=[EventType.QUIZ_STARTED]
    )
    assert total == 2
    page, total = svc.feed(user_id=owner.id, project_id=project.id, page=2, page_size=2)
    assert total == 4 and len(page) == 2
    future, total = svc.feed(
        user_id=owner.id,
        project_id=project.id,
        since=datetime.now(UTC) + timedelta(days=1),
    )
    assert total == 0 and future == []
    with pytest.raises(NotFoundError):
        svc.feed(user_id=owner.id, project_id=uuid.uuid4())


# ------------------------------------------------------------- dashboard


def _populated(session):
    owner, project, concepts = _seed_concepts(session, ["TCP", "UDP"])
    _complete(
        session,
        owner,
        project,
        [
            _perf(concepts["TCP"].id, "TCP"),
            _perf(concepts["UDP"].id, "UDP", norm=0.0, correct=0, incorrect=1, recent=["I"]),
        ],
        T0,
    )
    return owner, project, concepts


def test_dashboard_empty_project_honest(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    summary = _analytics(session).dashboard_summary(user_id=owner.id, project_id=project.id)
    assert summary.has_learning_evidence is False
    assert summary.overall_mastery is None
    assert summary.average_assessment_score is None
    assert summary.growth_status is None
    # Project creation itself is activity; cold-start honesty is about
    # mastery/scores (null), not about hiding the creation event.
    assert summary.last_activity_at is not None
    assert summary.assessment_count == 0
    assert summary.materials_count == 0
    # No zeros-as-failure anywhere.
    assert "0%" not in str(summary)


def test_dashboard_populated_metrics(session: Session) -> None:
    owner, project, concepts = _populated(session)
    summary = _analytics(session).dashboard_summary(user_id=owner.id, project_id=project.id)
    assert summary.project_name == project.name
    assert summary.has_learning_evidence is True
    assert summary.assessment_count == 1
    assert summary.questions_answered == 2
    assert summary.questions_correct == 1
    assert summary.questions_incorrect == 1
    assert summary.questions_partial == 0
    assert summary.average_assessment_score == pytest.approx(0.5)
    assert summary.overall_mastery == pytest.approx((0.625 + 0.375) / 2)
    assert summary.mastery_confidence is not None
    assert summary.growth_status is not None
    assert summary.active_recommendations >= 0
    assert summary.last_activity_at is not None
    assert 0.0 <= (summary.overall_mastery or 0) <= 1.0


def test_dashboard_material_knowledge_counts(session: Session) -> None:
    from app.models.enums import MaterialStatus
    from app.models.materials import Document, DocumentChunk
    from app.repositories.materials import MaterialRepository

    owner, project, _ = _seed_concepts(session, ["TCP"])
    mat = MaterialRepository(session).create(project_id=project.id, name="Doc")
    mat.status = MaterialStatus.READY
    session.flush()
    doc = Document(material_id=mat.id, project_id=project.id, page_count=3)
    session.add(doc)
    session.flush()
    for i in range(4):
        session.add(
            DocumentChunk(
                document_id=doc.id,
                project_id=project.id,
                chunk_index=i,
                content=f"chunk {i}",
                page_start=1,
                page_end=1,
            )
        )
    session.commit()
    summary = _analytics(session).dashboard_summary(user_id=owner.id, project_id=project.id)
    assert summary.materials_count == 1
    assert summary.materials_ready == 1
    assert summary.materials_failed == 0
    assert summary.documents_count == 1
    assert summary.pages_count == 3
    assert summary.chunks_count == 4
    assert summary.concepts_count == 1


def test_dashboard_archived_excluded(session: Session) -> None:
    from datetime import datetime as dt

    from app.repositories.materials import MaterialRepository

    owner = make_user(session)
    project = make_project(session, owner)
    mat = MaterialRepository(session).create(project_id=project.id, name="Old")
    mat.archived_at = dt.now(UTC)
    session.commit()
    summary = _analytics(session).dashboard_summary(user_id=owner.id, project_id=project.id)
    assert summary.materials_count == 0


def test_dashboard_tutor_counts(session: Session) -> None:
    from app.models.enums import MessageRole
    from app.models.tutor import Conversation, Message

    owner, project, _ = _seed_concepts(session, ["TCP"])
    conv = Conversation(project_id=project.id, user_id=owner.id, title="t")
    session.add(conv)
    session.flush()
    session.add(Message(conversation_id=conv.id, role=MessageRole.USER, content="hi"))
    session.add(Message(conversation_id=conv.id, role=MessageRole.ASSISTANT, content="hello"))
    session.commit()
    summary = _analytics(session).dashboard_summary(user_id=owner.id, project_id=project.id)
    assert summary.tutor_conversations == 1
    assert summary.tutor_messages == 2
    assert summary.has_learning_evidence is True


def test_activity_timeline_summaries_and_filter(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    events = _events(session)
    events.record(
        event_type=EventType.MATERIAL_UPLOADED,
        user_id=owner.id,
        project_id=project.id,
        entity_type="material",
        entity_id=uuid.uuid4(),
        payload={"material_id": "m", "name": "OS Notes.pdf"},
    )
    session.commit()
    events.record(
        event_type=EventType.TUTOR_MESSAGE,
        user_id=owner.id,
        project_id=project.id,
        entity_type="message",
        entity_id=uuid.uuid4(),
    )
    session.commit()
    events.record(event_type=EventType.EMBEDDING_STARTED, user_id=owner.id, project_id=project.id)
    session.commit()
    items = _analytics(session).activity(user_id=owner.id, project_id=project.id)
    # Newest first; EMBEDDING_STARTED is pipeline-internal (excluded), while
    # PROJECT_CREATED from setup is a genuine milestone.
    assert [i.summary for i in items] == [
        "Asked the tutor",
        "Uploaded — OS Notes.pdf",
        "Created project — Test Project",
    ]
    assert all(i.resource_id is not None or i.event_type == EventType.TUTOR_MESSAGE for i in items)
    assert all("password" not in str(i.metadata) for i in items)
    only_uploads = _analytics(session).activity(
        user_id=owner.id, project_id=project.id, event_types=[EventType.MATERIAL_UPLOADED]
    )
    assert len(only_uploads) == 1
    with pytest.raises(BadRequestError):
        _analytics(session).activity(user_id=owner.id, project_id=project.id, event_types=["BOGUS"])  # type: ignore[list-item]


def test_activity_by_day_zero_filled_and_all(session: Session) -> None:
    owner, project, _ = _seed_concepts(session, ["TCP"])
    events = _events(session)
    events.record(event_type=EventType.QUIZ_STARTED, user_id=owner.id, project_id=project.id)
    session.commit()
    week = _analytics(session).activity_by_day(user_id=owner.id, project_id=project.id, window="7d")
    assert len(week) == 7
    # Setup emits PROJECT_CREATED too; today holds both rows.
    assert sum(d.count for d in week) >= 2
    assert week[-1].count >= 2  # today
    everything = _analytics(session).activity_by_day(
        user_id=owner.id, project_id=project.id, window="all"
    )
    assert len(everything) == 1 and everything[0].count == 2
    with pytest.raises(BadRequestError):
        _analytics(session).activity_by_day(user_id=owner.id, project_id=project.id, window="99y")


def test_mastery_trend_reuses_growth_history(session: Session) -> None:
    owner, project, concepts = _seed_concepts(session, ["TCP"])
    _complete(session, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0)
    _complete(session, owner, project, [_perf(concepts["TCP"].id, "TCP")], T0 + timedelta(days=2))
    points = _analytics(session).mastery_trend(user_id=owner.id, project_id=project.id)
    assert len(points) == 2
    assert points[0].date <= points[1].date
    assert all(0.0 <= p.score <= 1.0 for p in points)


def test_dashboard_query_count_bounded(session: Session) -> None:
    """N+1 guard: the whole summary must stay well under 30 statements."""
    owner, project, concepts = _seed_concepts(session, ["A", "B", "C"])
    _complete(
        session,
        owner,
        project,
        [
            _perf(concepts["A"].id, "A"),
            _perf(concepts["B"].id, "B"),
            _perf(concepts["C"].id, "C", norm=0.0, correct=0, incorrect=1, recent=["I"]),
        ],
        T0,
    )
    statements = []

    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.strip().upper().startswith("SELECT"):
            statements.append(statement)

    from sqlalchemy import event as sa_event

    bind = session.get_bind()
    sa_event.listen(bind, "before_cursor_execute", _count)
    try:
        _analytics(session).dashboard_summary(user_id=owner.id, project_id=project.id)
    finally:
        sa_event.remove(bind, "before_cursor_execute", _count)
    assert len(statements) < 30, f"{len(statements)} SELECTs"


# ------------------------------------------------------------- routes + isolation


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


def test_routes_dashboard_activity_events(session: Session) -> None:
    owner, project, _ = _populated(session)
    app = _route_client(session, owner)
    try:
        client = TestClient(app)
        dashboard = client.get(f"/api/v1/projects/{project.id}/analytics/dashboard")
        assert dashboard.status_code == 200, dashboard.text
        body = dashboard.json()
        assert body["has_learning_evidence"] is True
        assert body["assessment_count"] == 1
        assert body["overall_mastery"] == pytest.approx(0.5)
        assert "storage_key" not in dashboard.text

        activity = client.get(f"/api/v1/projects/{project.id}/analytics/activity?limit=5")
        assert activity.status_code == 200
        assert activity.json()["page_size"] == 5

        by_day = client.get(f"/api/v1/projects/{project.id}/analytics/activity-by-day?range=7d")
        assert by_day.status_code == 200
        assert len(by_day.json()) == 7

        trend = client.get(f"/api/v1/projects/{project.id}/analytics/mastery-trend")
        assert trend.status_code == 200
        assert len(trend.json()) == 1

        events = client.get(f"/api/v1/projects/{project.id}/events?page_size=5")
        assert events.status_code == 200
        assert events.json()["total"] >= 1
        first = events.json()["items"][0]
        assert set(first) >= {"id", "event_type", "created_at", "resource_id", "metadata"}

        bad_range = client.get(f"/api/v1/projects/{project.id}/analytics/activity?range=99y")
        assert bad_range.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_routes_isolation(session: Session) -> None:
    owner, project, _ = _populated(session)
    stranger = make_user(session, email="stranger@example.com")
    other = make_project(session, stranger)
    app = _route_client(session, stranger)
    try:
        client = TestClient(app)
        assert client.get(f"/api/v1/projects/{project.id}/analytics/dashboard").status_code == 404
        assert client.get(f"/api/v1/projects/{project.id}/analytics/activity").status_code == 404
        assert client.get(f"/api/v1/projects/{project.id}/events").status_code == 404
        assert client.get(f"/api/v1/projects/{other.id}/analytics/dashboard").status_code == 200
    finally:
        app.dependency_overrides.clear()
