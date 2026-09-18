"""Project isolation: User A can never read User B's project-owned data through any
scoped repository method — not just at the auth layer, but at the data layer."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.enums import MasterySource, RecommendationType
from app.repositories.assessments import AssessmentRepository, QuizRepository
from app.repositories.intelligence import MasteryRepository, RecommendationRepository
from app.repositories.knowledge import ConceptRepository, ConversationRepository
from app.repositories.materials import MaterialRepository
from app.repositories.projects import ProjectRepository
from app.services.mastery_service import MasteryService
from app.services.project_service import ProjectService
from tests.conftest import make_project, make_user


@pytest.fixture()
def two_tenants(session: Session) -> tuple:
    user_a = make_user(session, email="a@example.com")
    user_b = make_user(session, email="b@example.com")
    project_a = make_project(session, user_a, name="A project")
    project_b = make_project(session, user_b, name="B project")

    mat_a = MaterialRepository(session).create(project_id=project_a.id, name="A mat")
    convo_a = ConversationRepository(session).create(project_id=project_a.id, user_id=user_a.id)
    quiz_a = QuizRepository(session).create(project_id=project_a.id, title="A quiz")
    concept_a, _ = ConceptRepository(session).get_or_create(
        project_id=project_a.id, name="A concept"
    )
    session.commit()
    return {
        "a": user_a,
        "b": user_b,
        "pa": project_a,
        "pb": project_b,
        "mat_a": mat_a,
        "convo_a": convo_a,
        "quiz_a": quiz_a,
        "concept_a": concept_a,
    }


def test_project_root_isolation(session: Session, two_tenants: dict) -> None:
    projects = ProjectRepository(session)
    assert projects.get_for_user(two_tenants["pa"].id, two_tenants["a"].id) is not None
    # Cross-tenant root lookup returns nothing — no exception, no leak.
    assert projects.get_for_user(two_tenants["pa"].id, two_tenants["b"].id) is None
    assert projects.get_for_user(two_tenants["pb"].id, two_tenants["a"].id) is None


def test_material_conversation_quiz_isolation(session: Session, two_tenants: dict) -> None:
    t = two_tenants
    assert MaterialRepository(session).get_for_project(t["mat_a"].id, t["pb"].id) is None
    assert (
        ConversationRepository(session).get_for_project(t["convo_a"].id, t["pb"].id, t["b"].id)
        is None
    )
    assert QuizRepository(session).get_for_project(t["quiz_a"].id, t["pb"].id) is None
    assert ConceptRepository(session).get_for_project(t["concept_a"].id, t["pb"].id) is None
    assert AssessmentRepository(session).get_for_project(t["quiz_a"].id, t["pb"].id) is None


def test_mastery_recommendation_isolation(session: Session, two_tenants: dict) -> None:
    t = two_tenants
    mastery_svc = MasteryService(session)
    mastery_svc.record_observation(
        user_id=t["a"].id,
        project_id=t["pa"].id,
        concept_id=t["concept_a"].id,
        score=55.0,
        source=MasterySource.QUIZ,
    )
    rec = RecommendationRepository(session).create(
        project_id=t["pa"].id,
        user_id=t["a"].id,
        type=RecommendationType.REVIEW_CONCEPT,
        title="Review",
        concept_id=t["concept_a"].id,
    )
    session.commit()

    mastery_repo = MasteryRepository(session)
    assert (
        mastery_repo.get_for_user(
            user_id=t["b"].id, project_id=t["pa"].id, concept_id=t["concept_a"].id
        )
        is None
    )
    # Same concept id, wrong project/user pair -> nothing.
    assert (
        mastery_repo.get_for_user(
            user_id=t["a"].id, project_id=t["pb"].id, concept_id=t["concept_a"].id
        )
        is None
    )
    recs = RecommendationRepository(session)
    assert recs.get_for_project(rec.id, t["pa"].id, t["b"].id) is None
    assert recs.get_for_project(rec.id, t["pb"].id, t["a"].id) is None
    items, total = recs.list_active(t["pb"].id, t["b"].id)
    assert total == 0 and items == []


def test_service_gate_rejects_cross_tenant(session: Session, two_tenants: dict) -> None:
    t = two_tenants
    svc = ProjectService(session)
    # 404 (not 403): cross-tenant existence is never disclosed.
    with pytest.raises(NotFoundError):
        svc.require_project(user_id=t["b"].id, project_id=t["pa"].id)
    with pytest.raises(NotFoundError):
        MasteryService(session).record_observation(
            user_id=t["b"].id,
            project_id=t["pa"].id,
            concept_id=t["concept_a"].id,
            score=10.0,
            source=MasterySource.SYSTEM,
        )
