"""Same-user cross-project IDOR: resources of Project A must never resolve
through Project B routes/services, in either direction.

Cross-TENANT isolation lives in test_project_isolation.py; this suite covers
the subtler same-owner case (one learner, two projects): every service call
and HTTP route below must behave as if the foreign resource does not exist
(404 / NotFoundError / empty), never leaking content or existence beyond the
non-disclosing 404 already used for missing rows.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.base import EmbedRequest
from app.ai.fakes import DeterministicEmbeddingProvider
from app.core.exceptions import NotFoundError
from app.models.enums import MaterialStatus, MessageRole
from app.repositories.assessments import QuizRepository
from app.repositories.knowledge import ConceptRepository, MessageRepository
from app.repositories.materials import MaterialRepository
from app.services.assessment_service import AssessmentService
from app.services.knowledge_service import KnowledgeService
from app.services.learning_context_service import LearningContextService
from app.services.mastery_service import MasteryService
from app.services.material_service import MaterialService
from app.services.recommendation_service import RecommendationService
from app.services.tutor_service import TutorService
from tests.conftest import make_project, make_user


@pytest.fixture()
def same_owner_two_projects(session: Session) -> dict:
    """One user, two projects; Project A holds one of everything."""
    from app.models.materials import Document, DocumentChunk

    user = make_user(session)
    project_a = make_project(session, user, name="Project A")
    project_b = make_project(session, user, name="Project B")

    mat_a = MaterialRepository(session).create(project_id=project_a.id, name="A notes")
    mat_a.status = MaterialStatus.READY
    session.flush()
    doc_a = Document(material_id=mat_a.id, project_id=project_a.id, page_count=1)
    session.add(doc_a)
    session.flush()
    chunk_text = "Mitosis divides one cell into two identical daughter cells."
    vec = asyncio.run(
        DeterministicEmbeddingProvider(dimensions=768).embed(EmbedRequest(texts=[chunk_text]))
    ).embeddings[0]
    chunk_a = DocumentChunk(
        document_id=doc_a.id,
        project_id=project_a.id,
        chunk_index=0,
        content=chunk_text,
        page_start=1,
        page_end=1,
        embedding=list(vec),
    )
    session.add(chunk_a)
    session.flush()
    concept_a, _ = ConceptRepository(session).get_or_create(
        project_id=project_a.id, name="Mitosis", description="Cell division."
    )
    tutor = TutorService(session)
    conv_a = tutor.create_conversation(user_id=user.id, project_id=project_a.id)
    MessageRepository(session).append(
        conversation_id=conv_a.id, role=MessageRole.USER, content="Explain mitosis from my notes."
    )
    quiz_a = QuizRepository(session).create(project_id=project_a.id, title="A quiz")
    session.commit()
    return {
        "user": user,
        "pa": project_a,
        "pb": project_b,
        "mat_a": mat_a,
        "conv_a": conv_a,
        "quiz_a": quiz_a,
        "concept_a": concept_a,
    }


def _svc(session: Session, cls):
    from app.core.config import Settings

    try:
        return cls(session, settings=Settings(test_fake_ai=True))
    except TypeError:
        return cls(session)


# ------------------------------------------------------- tutor / conversation


def test_conversation_a_invisible_through_project_b(
    session: Session, same_owner_two_projects
) -> None:
    t = same_owner_two_projects
    svc = _svc(session, TutorService)
    with pytest.raises(NotFoundError):
        svc.get_conversation(
            user_id=t["user"].id, project_id=t["pb"].id, conversation_id=t["conv_a"].id
        )
    with pytest.raises(NotFoundError):
        svc.get_messages(
            user_id=t["user"].id, project_id=t["pb"].id, conversation_id=t["conv_a"].id
        )
    # Listing B never contains A's conversation.
    convos = svc.list_conversations(user_id=t["user"].id, project_id=t["pb"].id)
    assert all(c.project_id == t["pb"].id for c in convos)
    assert t["conv_a"].id not in {c.id for c in convos}


def test_message_send_to_a_through_project_b_rejected(
    session: Session, same_owner_two_projects
) -> None:
    t = same_owner_two_projects
    svc = _svc(session, TutorService)
    with pytest.raises(NotFoundError):
        asyncio.run(
            svc.send_message(
                user_id=t["user"].id,
                project_id=t["pb"].id,
                conversation_id=t["conv_a"].id,
                content="Hi from B",
            )
        )


def test_reverse_direction_a_route_rejects_b_resource(
    session: Session, same_owner_two_projects
) -> None:
    t = same_owner_two_projects
    svc = _svc(session, TutorService)
    conv_b = svc.create_conversation(user_id=t["user"].id, project_id=t["pb"].id)
    with pytest.raises(NotFoundError):
        svc.get_conversation(user_id=t["user"].id, project_id=t["pa"].id, conversation_id=conv_b.id)


# ------------------------------------------------------------------ materials


def test_material_a_invisible_through_project_b(session: Session, same_owner_two_projects) -> None:
    t = same_owner_two_projects
    svc = _svc(session, MaterialService)
    with pytest.raises(NotFoundError):
        svc.get_material_detail(
            user_id=t["user"].id, project_id=t["pb"].id, material_id=t["mat_a"].id
        )
    items, total, _, _ = svc.list_materials(
        user_id=t["user"].id, project_id=t["pb"].id, page=1, page_size=20
    )
    assert total == 0 and items == []


# --------------------------------------------------------------------- quizzes


def test_quiz_a_invisible_through_project_b(session: Session, same_owner_two_projects) -> None:
    t = same_owner_two_projects
    svc = _svc(session, AssessmentService)
    with pytest.raises(NotFoundError):
        svc.get_quiz(user_id=t["user"].id, project_id=t["pb"].id, quiz_id=t["quiz_a"].id)
    assert svc.list_quizzes(user_id=t["user"].id, project_id=t["pb"].id) == []
    with pytest.raises(NotFoundError):
        asyncio.run(
            svc.start_attempt(user_id=t["user"].id, project_id=t["pb"].id, quiz_id=t["quiz_a"].id)
        )


# ------------------------------------------------- mastery / recommendations


def test_mastery_and_recommendations_do_not_cross(
    session: Session, same_owner_two_projects
) -> None:
    t = same_owner_two_projects
    mastery = _svc(session, MasteryService)
    estimates = mastery.scores_for_concepts(
        user_id=t["user"].id, project_id=t["pb"].id, concept_ids=[t["concept_a"].id]
    )
    assert estimates == {}
    recs = _svc(session, RecommendationService)
    items, total = recs.list_active(user_id=t["user"].id, project_id=t["pb"].id)
    assert total == 0 and items == []


# ------------------------------------------------- knowledge / learning state


def test_rag_search_in_b_ignores_a_chunks(session: Session, same_owner_two_projects) -> None:
    t = same_owner_two_projects
    svc = _svc(session, KnowledgeService)
    result = asyncio.run(
        svc.search(
            user_id=t["user"].id,
            project_id=t["pb"].id,
            query="Mitosis divides one cell into two identical daughter cells.",
        )
    )
    assert result["insufficient_evidence"] is True
    assert result["results"] == []


def test_learning_context_in_b_has_no_a_data(session: Session, same_owner_two_projects) -> None:
    t = same_owner_two_projects
    text = LearningContextService(session).context_for_tutor(
        user_id=t["user"].id, project_id=t["pb"].id
    )
    assert "Mitosis" not in text


# ------------------------------------------------------------------ HTTP layer


@pytest.fixture()
def api_client(session: Session, monkeypatch):
    from app.core import config as config_module
    from app.db.session import get_db
    from app.main import create_app

    monkeypatch.setenv("TEST_FAKE_AI", "true")
    config_module.get_settings.cache_clear()
    app = create_app()

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    yield TestClient(app, raise_server_exceptions=False)
    config_module.get_settings.cache_clear()


def _register(api_client: TestClient, email: str) -> dict:
    res = api_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass123", "display_name": "T"},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _two_projects(api_client: TestClient, token: str) -> tuple[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    space = api_client.post("/api/v1/spaces", headers=headers, json={"name": "S"}).json()

    def _mk(name: str) -> str:
        return api_client.post(
            "/api/v1/projects", headers=headers, json={"space_id": space["id"], "name": name}
        ).json()["id"]

    return _mk("Project A"), _mk("Project B")


def test_http_cross_project_conversation_is_404(session: Session, api_client: TestClient) -> None:
    token = _register(api_client, "idor@example.com")["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    pa_id, pb_id = _two_projects(api_client, token)
    conv = api_client.post(
        f"/api/v1/projects/{pa_id}/conversations", headers=headers, json={}
    ).json()
    # Direct-ID substitution: A's conversation through B's route.
    res = api_client.get(f"/api/v1/projects/{pb_id}/conversations/{conv['id']}", headers=headers)
    assert res.status_code == 404, res.text
    res = api_client.get(
        f"/api/v1/projects/{pb_id}/conversations/{conv['id']}/messages", headers=headers
    )
    assert res.status_code == 404, res.text
    res = api_client.post(
        f"/api/v1/projects/{pb_id}/conversations/{conv['id']}/messages",
        headers=headers,
        json={"content": "Hello from B?"},
    )
    assert res.status_code == 404, res.text
    # B's own list never contains A's conversation.
    listed = api_client.get(f"/api/v1/projects/{pb_id}/conversations", headers=headers).json()
    assert all(c["project_id"] == pb_id for c in listed)
    assert conv["id"] not in {c["id"] for c in listed}
    # Quizzes/materials cross-checks at the HTTP boundary.
    res = api_client.get(f"/api/v1/projects/{pb_id}/quizzes/{uuid.uuid4()}", headers=headers)
    assert res.status_code == 404
