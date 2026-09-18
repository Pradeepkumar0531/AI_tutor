"""Knowledge layer: status derivation, concept upserts/provenance/relationships,
reprocess rules, and the HTTP API contracts (auth, isolation, pagination,
limits, no-embedding-leak)."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.fakes import DeterministicEmbeddingProvider
from app.ai.schemas import ConceptExtractionResult
from app.core.config import Settings
from app.models.enums import ConceptRelationType, JobStatus, MaterialStatus
from app.models.knowledge import Concept, ConceptRelationship
from app.models.materials import Document, DocumentChunk, Material
from app.services.knowledge_service import (
    KnowledgeService,
    ProvenanceEntry,
    merge_provenance,
)
from tests.conftest import make_project, make_user


def _fake_settings(**kwargs) -> Settings:
    kwargs.setdefault("test_fake_ai", True)
    return Settings(**kwargs)


def _fake_service():
    from app.ai.embeddings import EmbeddingService

    return EmbeddingService(
        DeterministicEmbeddingProvider(dimensions=768),
        model="models/gemini-embedding-001",
        dimensions=768,
    )


def _ready_material(
    session: Session, project, texts: list[str], *, embeddings: bool = False
) -> Material:
    """READY material + document + one chunk per text, optionally embedded."""
    from app.repositories.materials import MaterialRepository

    mat = MaterialRepository(session).create(project_id=project.id, name="Doc")
    mat.status = MaterialStatus.READY
    session.flush()
    doc = Document(material_id=mat.id, project_id=project.id, page_count=1)
    session.add(doc)
    session.flush()
    vectors = (
        asyncio.run(_fake_service().embed_texts(texts if embeddings else [])) if embeddings else []
    )
    for i, text in enumerate(texts):
        session.add(
            DocumentChunk(
                document_id=doc.id,
                project_id=project.id,
                chunk_index=i,
                content=text,
                page_start=1,
                page_end=1,
                embedding=list(vectors[i]) if embeddings else None,
            )
        )
    session.commit()
    return mat


# ------------------------------------------------------------- status


def test_status_pending_when_empty(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    status = KnowledgeService(session).get_status(user_id=owner.id, project_id=project.id)
    assert status.status == "PENDING"
    assert (status.chunks_total, status.chunks_embedded, status.concepts) == (0, 0, 0)


def test_status_ready_when_fully_embedded(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    _ready_material(session, project, ["alpha beta", "gamma delta"], embeddings=True)
    status = KnowledgeService(session).get_status(user_id=owner.id, project_id=project.id)
    assert status.status == "READY"
    assert (status.chunks_total, status.chunks_embedded) == (2, 2)


def test_status_processing_when_partial(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    mat = _ready_material(session, project, ["one two", "three four"], embeddings=False)
    # Embed exactly one chunk manually: partial without any job row.
    from app.repositories.materials import ChunkRepository

    chunks = ChunkRepository(session).list_unembedded(
        session.query(Document).filter_by(material_id=mat.id).one().id, project.id
    )
    assert len(chunks) == 2
    vec = asyncio.run(_fake_service().embed_texts([chunks[0].content]))[0]
    ChunkRepository(session).write_embeddings([(chunks[0].id, vec)])
    session.commit()
    status = KnowledgeService(session).get_status(user_id=owner.id, project_id=project.id)
    assert status.status == "PROCESSING"
    assert (status.chunks_total, status.chunks_embedded) == (2, 1)


def test_status_failed_and_unauthorized(session: Session) -> None:
    from app.core.exceptions import NotFoundError

    owner = make_user(session)
    project = make_project(session, owner)
    mat = _ready_material(session, project, ["lonely chunk here"])
    svc = KnowledgeService(session)
    job = svc.ensure_knowledge_job(project_id=project.id, material_id=mat.id)
    job.status = JobStatus.FAILED
    session.commit()
    assert svc.get_status(user_id=owner.id, project_id=project.id).status == "FAILED"
    stranger = make_user(session, email="stranger@example.com")
    with pytest.raises(NotFoundError):
        svc.get_status(user_id=stranger.id, project_id=project.id)


# ------------------------------------------------------------- concepts


def test_upsert_dedupes_and_merges_provenance(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    svc = KnowledgeService(session)
    entry = ProvenanceEntry(
        material_id=uuid.uuid4(), material_name="M", chunk_ids=[uuid.uuid4()], pages=[3]
    )
    first = svc.upsert_concepts(
        project_id=project.id,
        extraction=ConceptExtractionResult.model_validate(
            {"concepts": [{"name": "  Mitosis  ", "description": "Cell division."}]}
        ),
        provenance=entry,
        model="test",
    )
    assert (first.created, first.updated) == (1, 0)
    session.commit()

    second = svc.upsert_concepts(
        project_id=project.id,
        extraction=ConceptExtractionResult.model_validate(
            {"concepts": [{"name": "mitosis", "description": ""}]}
        ),
        provenance=ProvenanceEntry(
            material_id=uuid.uuid4(), material_name="M2", chunk_ids=[], pages=[1]
        ),
        model="test",
    )
    assert (second.created, second.updated) == (0, 0)  # same normalized name
    session.commit()
    concept = session.query(Concept).filter_by(project_id=project.id).one()
    assert concept.description == "Cell division."  # non-empty description kept
    assert concept.concept_metadata is not None
    by_name = {m["material_name"]: m for m in concept.concept_metadata["materials"]}
    assert set(by_name) == {"M", "M2"}  # provenance union, keyed by material
    assert by_name["M"]["pages"] == [3]


def test_relationships_validated_and_project_scoped(session: Session) -> None:
    owner = make_user(session)
    project = make_project(session, owner)
    other = make_project(session, owner)
    svc = KnowledgeService(session)
    entry = ProvenanceEntry(material_id=uuid.uuid4(), material_name="M")
    stats = svc.upsert_concepts(
        project_id=project.id,
        extraction=ConceptExtractionResult.model_validate(
            {
                "concepts": [{"name": "Alpha"}, {"name": "Beta"}, {"name": "Gamma"}],
                "relationships": [
                    {"source": "Alpha", "target": "Beta", "type": "PREREQUISITE"},
                    {"source": "Beta", "target": "Beta", "type": "RELATED"},
                    {"source": "Alpha", "target": "Missing", "type": "RELATED"},
                    {"source": "Alpha", "target": "Gamma", "type": "BOGUS"},
                    {"source": "Alpha", "target": "Beta", "type": "PREREQUISITE"},
                ],
            }
        ),
        provenance=entry,
        model="test",
    )
    assert stats.relationships_created == 1
    assert stats.relationships_skipped == 4  # self, missing, bad type, duplicate
    session.commit()
    rel = session.query(ConceptRelationship).one()
    assert rel.relationship_type == ConceptRelationType.PREREQUISITE
    assert rel.project_id == project.id

    # The database itself refuses cross-project endpoints (composite FKs).
    foreign, _ = KnowledgeService(session).concepts.get_or_create(
        project_id=other.id, name="Foreign"
    )
    session.flush()
    local = session.query(Concept).filter_by(project_id=project.id, normalized_name="alpha").one()
    bad = ConceptRelationship(
        project_id=project.id,
        source_concept_id=local.id,
        target_concept_id=foreign.id,
        relationship_type=ConceptRelationType.RELATED,
    )
    session.add(bad)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_merge_provenance_is_deterministic() -> None:
    from app.services.knowledge_service import ProvenanceEntry

    mid = uuid.uuid4()
    merged = merge_provenance(
        {"source": "ai-extraction", "model": "m", "materials": [{"material_id": str(mid)}]},
        entry=ProvenanceEntry(material_id=mid, material_name="M2", pages=[2]),
        model="m2",
    )
    assert len(merged["materials"]) == 1
    assert merged["materials"][0]["material_name"] == "M2"  # replaced, not duplicated
    assert merged["model"] == "m2"


# ------------------------------------------------------------- reprocess


def test_reprocess_rules(session: Session) -> None:
    from app.core.exceptions import ConflictError, NotFoundError

    owner = make_user(session)
    project = make_project(session, owner)
    mat = _ready_material(session, project, ["some content here"])
    svc = KnowledgeService(session)

    first = svc.reprocess_material_knowledge(
        user_id=owner.id, project_id=project.id, material_id=mat.id
    )
    assert first["job_status"] == "QUEUED"
    session.commit()

    # Active job blocks a second reprocess.
    with pytest.raises(ConflictError):
        svc.reprocess_material_knowledge(
            user_id=owner.id, project_id=project.id, material_id=mat.id
        )
    session.rollback()

    # Unknown material / foreign project stay silent.
    with pytest.raises(NotFoundError):
        svc.reprocess_material_knowledge(
            user_id=owner.id, project_id=project.id, material_id=uuid.uuid4()
        )
    stranger = make_user(session, email="x@example.com")
    with pytest.raises(NotFoundError):
        svc.reprocess_material_knowledge(
            user_id=stranger.id, project_id=project.id, material_id=mat.id
        )


# ------------------------------------------------------------- API contracts


@pytest.fixture(autouse=True)
def _fake_ai(monkeypatch):
    """API paths read global Settings: enable the deterministic fake providers
    (no credentials, no network) and reset the settings cache afterwards."""
    from app.core.config import get_settings

    monkeypatch.setenv("TEST_FAKE_AI", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_broker(monkeypatch):
    """Never touch a real broker in route tests: dispatch is a separately
    tested contract (see test_dispatch_knowledge); here it always 'succeeds'."""
    import app.api.routes.knowledge as routes

    monkeypatch.setattr(routes, "dispatch_knowledge", lambda _mid: True)


@pytest.fixture()
def client(session) -> TestClient:
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _register(client: TestClient, email: str) -> str:
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePass123", "display_name": "T"},
    )
    assert res.status_code == 201, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _project(client: TestClient, token: str) -> str:
    space = client.post("/api/v1/spaces", headers=_auth(token), json={"name": "S"}).json()
    project = client.post(
        "/api/v1/projects",
        headers=_auth(token),
        json={"space_id": space["id"], "name": "P"},
    ).json()
    return project["id"]


def _seed_embedded(session: Session, project_id: uuid.UUID, texts: list[str]) -> None:
    from app.models.learning import Project
    from app.repositories.materials import MaterialRepository

    project = session.get(Project, project_id)
    assert project is not None
    mat = MaterialRepository(session).create(project_id=project.id, name="Doc")
    from app.models.enums import MaterialStatus as MS

    mat.status = MS.READY
    session.flush()
    doc = Document(material_id=mat.id, project_id=project.id, page_count=1)
    session.add(doc)
    session.flush()
    vectors = asyncio.run(_fake_service().embed_texts(texts))
    for i, text in enumerate(texts):
        session.add(
            DocumentChunk(
                document_id=doc.id,
                project_id=project.id,
                chunk_index=i,
                content=text,
                page_start=i + 1,
                page_end=i + 1,
            )
        )
    session.flush()
    # Bulk-write vectors like the job would (validated, transactional).
    from app.repositories.materials import ChunkRepository

    repo = ChunkRepository(session)
    chunks = repo.list_unembedded(doc.id, project.id, limit=100)
    repo.write_embeddings([(c.id, list(v)) for c, v in zip(chunks, vectors, strict=True)])
    session.commit()


def test_search_contracts(client: TestClient, session: Session) -> None:
    from app.models.users import User

    token = _register(client, "searcher@example.com")
    owner = session.query(User).filter_by(email="searcher@example.com").one()
    assert owner is not None
    project_id = uuid.UUID(_project(client, token))
    texts = [
        "Photosynthesis converts sunlight into chemical energy in plants.",
        "Mitochondria release energy as ATP through cellular respiration.",
        "Newtonian mechanics describes motion with three laws of motion.",
    ]
    _seed_embedded(session, project_id, texts)

    def search(body: dict, tok: str = token):
        return client.post(
            f"/api/v1/projects/{project_id}/knowledge/search", headers=_auth(tok), json=body
        )

    # Happy path: exact-match text ranks first with similarity 1.0.
    res = search({"query": texts[0]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["query"] == texts[0]
    assert body["insufficient_evidence"] is False
    assert body["results"][0]["similarity"] == 1.0
    assert body["results"][0]["text"] == texts[0]
    assert body["results"][0]["page_start"] == 1
    assert body["citations"][0]["chunk_id"] == body["results"][0]["chunk_id"]
    assert "Photosynthesis" in body["context"]
    assert "UNTRUSTED SOURCE MATERIAL" in body["context"]
    assert "embedding" not in res.text and "storage_key" not in res.text

    # top_k respected (exact match scores 1.0, above any threshold).
    assert len(search({"query": texts[0], "top_k": 1}).json()["results"]) == 1
    # Out-of-range top_k rejected at the boundary (service also clamps).
    assert search({"query": texts[0], "top_k": 500}).status_code == 422
    # Impossible threshold -> explicit insufficient evidence, still 200.
    thin = search({"query": "energy motion", "threshold": 1.0})
    assert thin.json()["insufficient_evidence"] is True
    assert thin.json()["results"] == [] and thin.json()["citations"] == []
    # Empty project -> insufficient evidence, no fabrication.
    stranger_token = _register(client, "empty@example.com")
    stranger_project = _project(client, stranger_token)
    res = client.post(
        f"/api/v1/projects/{stranger_project}/knowledge/search",
        headers=_auth(stranger_token),
        json={"query": "anything at all here"},
    )
    assert res.json()["insufficient_evidence"] is True

    # Auth matrix.
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/knowledge/search", json={"query": "x"}
        ).status_code
        == 401
    )
    other = _register(client, "other@example.com")
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/knowledge/search",
            headers=_auth(other),
            json={"query": "x"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/projects/{uuid.uuid4()}/knowledge/search",
            headers=_auth(token),
            json={"query": "x"},
        ).status_code
        == 404
    )
    # Validation.
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/knowledge/search",
            headers=_auth(token),
            json={"query": ""},
        ).status_code
        == 422
    )


def test_knowledge_status_and_concepts_endpoints(client: TestClient, session: Session) -> None:
    token = _register(client, "knower@example.com")
    project_id = uuid.UUID(_project(client, token))

    res = client.get(f"/api/v1/projects/{project_id}/knowledge", headers=_auth(token))
    assert res.json()["status"] == "PENDING"

    _seed_embedded(session, project_id, ["alpha beta gamma delta epsilon"])
    res = client.get(f"/api/v1/projects/{project_id}/knowledge", headers=_auth(token))
    body = res.json()
    assert body["status"] == "READY"
    assert body["totals"] == {
        "chunks_total": 1,
        "chunks_embedded": 1,
        "concepts": 0,
        "materials_ready": 1,
    }

    # Concepts via service upsert, read via API with pagination.
    from app.models.users import User

    assert session.query(User).filter_by(email="knower@example.com").one() is not None
    from app.repositories.materials import MaterialRepository

    material = MaterialRepository(session).create(project_id=project_id, name="M0")
    session.commit()
    svc = KnowledgeService(session)
    from app.ai.schemas import ConceptExtractionResult
    from app.services.knowledge_service import ProvenanceEntry

    for i in range(3):
        svc.upsert_concepts(
            project_id=project_id,
            extraction=ConceptExtractionResult.model_validate(
                {"concepts": [{"name": f"Concept {i}", "description": f"About {i}."}]}
            ),
            provenance=ProvenanceEntry(material_id=material.id, material_name="M0"),
            model="test",
        )
    session.commit()
    page1 = client.get(
        f"/api/v1/projects/{project_id}/concepts?page=1&page_size=2", headers=_auth(token)
    ).json()
    assert page1["total"] == 3 and len(page1["items"]) == 2
    cid = page1["items"][0]["id"]
    detail = client.get(
        f"/api/v1/projects/{project_id}/concepts/{cid}", headers=_auth(token)
    ).json()
    assert detail["name"].startswith("Concept")
    assert detail["materials"][0]["name"].startswith("M")
    assert detail["chunk_count"] >= 0 and isinstance(detail["pages"], list)

    other = _register(client, "nosy@example.com")
    assert (
        client.get(f"/api/v1/projects/{project_id}/concepts", headers=_auth(other)).status_code
        == 404
    )
    assert client.get(f"/api/v1/projects/{project_id}/concepts").status_code == 401


def test_reprocess_knowledge_endpoint(client: TestClient, session: Session) -> None:
    token = _register(client, "repro@example.com")
    project_id = uuid.UUID(_project(client, token))
    _seed_embedded(session, project_id, ["reset me please now"])
    mat = session.query(Material).filter_by(project_id=project_id).one()

    res = client.post(
        f"/api/v1/projects/{project_id}/materials/{mat.id}/reprocess-knowledge",
        headers=_auth(token),
    )
    assert res.status_code == 202, res.text
    assert res.json()["job_status"] == "QUEUED"
    session.expire_all()
    from app.repositories.materials import ChunkRepository

    total, embedded = ChunkRepository(session).count_embedded_for_material(mat.id)
    assert (total, embedded) == (1, 0)

    # Active job blocks a second call.
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/materials/{mat.id}/reprocess-knowledge",
            headers=_auth(token),
        ).status_code
        == 409
    )

    # Unknown material / foreign project stay silent.
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/materials/{uuid.uuid4()}/reprocess-knowledge",
            headers=_auth(token),
        ).status_code
        == 404
    )


def test_material_detail_carries_knowledge(client: TestClient, session: Session) -> None:
    token = _register(client, "detailer@example.com")
    project_id = uuid.UUID(_project(client, token))
    _seed_embedded(session, project_id, ["detail content here"])
    mat = session.query(Material).filter_by(project_id=project_id).one()
    res = client.get(f"/api/v1/projects/{project_id}/materials/{mat.id}", headers=_auth(token))
    assert res.status_code == 200, res.text
    knowledge = res.json()["knowledge"]
    assert knowledge == {
        "status": "READY",
        "embedded": 1,
        "total": 1,
        "image_count": 0,
        "images_by_page": {},
    }
